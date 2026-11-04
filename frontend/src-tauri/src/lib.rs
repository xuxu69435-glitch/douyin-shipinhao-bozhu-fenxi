use std::fs;
use std::net::TcpListener;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use hmac::{Hmac, Mac};
use sha2::Sha256;

use std::time::Duration;
use tauri::{Manager, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_dialog::DialogExt;

mod process_job;
mod smoke;
use process_job::ProcessJob;

#[derive(Clone)]
struct BackendConnection {
    base_url: String,
    token: String,
}

struct BackendState {
    connection: BackendConnection,
    child: Mutex<Option<CommandChild>>,
    job: Mutex<Option<ProcessJob>>,
    exiting: AtomicBool,
}

#[tauri::command]
async fn backend_request(
    state: State<'_, BackendState>,
    path: String,
    method: String,
    body: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    // Avoid open proxy behavior; the renderer can only call our own API.
    if !path.starts_with("/api/")
        || !path.chars().all(|c| c.is_ascii_alphanumeric() || "_-/".contains(c))
    {
        return Err("invalid API path".to_string());
    }
    if method != "GET" && method != "POST" {
        return Err("method not allowed".to_string());
    }
    let connection = state.connection.clone();
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(if path == "/api/settings/test" { 210 } else { 60 }))
        .build()
        .map_err(|e| e.to_string())?;
    let url = format!("{}{}", connection.base_url, path);
    let request = if method == "POST" { client.post(url) } else { client.get(url) }
        .header("X-Analyst-Token", connection.token);
    let request = if let Some(payload) = body { request.json(&payload) } else { request };
    let response = request.send().await.map_err(|e| format!("backend unavailable: {e}"))?;
    let status = response.status();
    let value: serde_json::Value = response.json().await.map_err(|e| e.to_string())?;
    if !status.is_success() {
        return Err(format!("HTTP {}: {}", status, value.get("detail").and_then(|x| x.as_str()).unwrap_or("request failed")));
    }
    Ok(value)
}

#[tauri::command]
async fn select_local_video(app: tauri::AppHandle) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        app.dialog().file().add_filter("视频", &["mp4", "mov", "mkv", "webm", "avi"])
            .blocking_pick_file().map(|file| file.into_path().map(|path| path.to_string_lossy().to_string())
                .map_err(|e| e.to_string())).transpose()
    }).await.map_err(|e| e.to_string())?
}

#[tauri::command]
async fn save_export(app: tauri::AppHandle, filename: String, content: String) -> Result<bool, String> {
    if filename.is_empty() || filename.contains(['/', '\\']) || content.len() > 20_000_000 {
        return Err("invalid export".to_string());
    }
    tauri::async_runtime::spawn_blocking(move || {
        if let Some(destination) = app.dialog().file().set_file_name(&filename).blocking_save_file() {
            let path = destination.into_path().map_err(|e| e.to_string())?;
            fs::write(path, content).map_err(|e| e.to_string())?;
            Ok(true)
        } else { Ok(false) }
    }).await.map_err(|e| e.to_string())?
}

#[tauri::command]
fn backend_media_url(state: State<'_, BackendState>, video_id: String) -> Result<String, String> {
    if uuid::Uuid::parse_str(&video_id).is_err() {
        return Err("invalid video ID".to_string());
    }
    let expires = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_secs() + 600;
    let mut mac = Hmac::<Sha256>::new_from_slice(state.connection.token.as_bytes())
        .map_err(|e| e.to_string())?;
    mac.update(format!("{}:{}", video_id, expires).as_bytes());
    let signature = hex::encode(mac.finalize().into_bytes());
    Ok(format!("{}/media/{}?expires={}&signature={}",
        state.connection.base_url, video_id, expires, signature))
}

fn stop_backend(handle: &tauri::AppHandle) {
    if let Some(state) = handle.try_state::<BackendState>() {
        if let Ok(mut guard) = state.job.lock() { drop(guard.take()); }
        if let Ok(mut guard) = state.child.lock() {
            if let Some(child) = guard.take() {
                let _ = child.kill();
            }
        }
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // Reserve an ephemeral loopback port; the sidecar must bind that same port.
            // An auth token prevents other local processes from impersonating our API.
            let listener = TcpListener::bind("127.0.0.1:0")?;
            let port = listener.local_addr()?.port();
            drop(listener);

            let smoke_mode = std::env::args().any(|argument| argument == "--smoke-test");
            let data_dir = if smoke_mode {
                std::path::PathBuf::from(std::env::var("ANALYST_SMOKE_DATA_DIR")
                    .map_err(|_| "smoke tests require an isolated ANALYST_SMOKE_DATA_DIR")?)
            } else { app.path().app_local_data_dir()? };
            if smoke_mode {
                if let Some(window) = app.get_webview_window("main") { window.hide()?; }
            }
            fs::create_dir_all(&data_dir)?;
            let token = uuid::Uuid::new_v4().simple().to_string();
            let command = app
                .shell()
                .sidecar("douyin-analyst-backend")?
                .current_dir(&data_dir)
                .env("ANALYST_BACKEND_PORT", port.to_string())
                .env("ANALYST_BACKEND_TOKEN", token.clone())
                .env("ANALYST_DATA_DIR", data_dir.to_string_lossy().to_string());
            let (mut rx, child) = command.spawn()?;
            let job = match ProcessJob::new(child.pid()) {
                Ok(job) => job,
                Err(error) => { let _ = child.kill(); return Err(error.into()); }
            };
            let event_handle = app.handle().clone();

            // Drain the pipe to prevent the child process blocking on a full pipe.
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Terminated(status) => {
                            eprintln!("[sidecar] terminated with code {:?}", status.code);
                            if let Some(state) = event_handle.try_state::<BackendState>() {
                                if let Ok(mut child) = state.child.lock() { child.take(); }
                            }
                            break;
                        }
                        CommandEvent::Stderr(data) => {
                            eprintln!("[sidecar] {}", String::from_utf8_lossy(&data));
                        }
                        _ => {}
                    }
                }
            });

            app.manage(BackendState {
                connection: BackendConnection {
                    base_url: format!("http://127.0.0.1:{port}"),
                    token,
                },
                child: Mutex::new(Some(child)),
                job: Mutex::new(Some(job)),
                exiting: AtomicBool::new(false),
            });
            if smoke_mode {
                let handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    let result = smoke::run(&handle).await;
                    let success = result.is_ok();
                    let report = result.unwrap_or_else(|error| serde_json::json!({"ok": false, "error": error}));
                    if let Ok(path) = std::env::var("ANALYST_SMOKE_REPORT") {
                        let _ = fs::write(path, serde_json::to_vec_pretty(&report).unwrap_or_default());
                    }
                    handle.exit(if success { 0 } else { 1 });
                });
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_request, backend_media_url, select_local_video, save_export])
        .build(tauri::generate_context!())
        .expect("failed to build Tauri application")
        .run(|app, event| {
            match event {
                tauri::RunEvent::ExitRequested { api, .. } => {
                    let state = app.state::<BackendState>();
                    if state.exiting.swap(true, Ordering::SeqCst) { return; }
                    api.prevent_exit();
                    let connection = state.connection.clone();
                    let handle = app.clone();
                    tauri::async_runtime::spawn(async move {
                        if let Ok(client) = reqwest::Client::builder().timeout(Duration::from_secs(2)).build() {
                            let _ = client.post(format!("{}/api/shutdown", connection.base_url))
                                .header("X-Analyst-Token", connection.token).send().await;
                        }
                        for _ in 0..12 {
                            let stopped = handle.state::<BackendState>().child.lock()
                                .map(|child| child.is_none()).unwrap_or(false);
                            if stopped { break; }
                            tokio_sleep().await;
                        }
                        stop_backend(&handle);
                        handle.exit(0);
                    });
                }
                tauri::RunEvent::Exit => stop_backend(app),
                _ => {}
            }
        });
}

async fn tokio_sleep() {
    // Use Tauri's blocking pool instead of adding another runtime dependency.
    let _ = tauri::async_runtime::spawn_blocking(|| std::thread::sleep(Duration::from_millis(250))).await;
}
