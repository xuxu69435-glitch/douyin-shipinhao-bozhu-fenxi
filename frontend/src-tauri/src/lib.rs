use std::fs;
use std::net::TcpListener;
use std::sync::Mutex;

use std::time::Duration;
use tauri::{Manager, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Clone)]
struct BackendConnection {
    base_url: String,
    token: String,
}

struct BackendState {
    connection: BackendConnection,
    child: Mutex<Option<CommandChild>>,
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
        .timeout(Duration::from_secs(15))
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

fn stop_backend(handle: &tauri::AppHandle) {
    if let Some(state) = handle.try_state::<BackendState>() {
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
        .setup(|app| {
            // Reserve an ephemeral loopback port; the sidecar must bind that same port.
            // An auth token prevents other local processes from impersonating our API.
            let listener = TcpListener::bind("127.0.0.1:0")?;
            let port = listener.local_addr()?.port();
            drop(listener);

            let data_dir = app.path().app_local_data_dir()?;
            fs::create_dir_all(&data_dir)?;
            let token = uuid::Uuid::new_v4().simple().to_string();
            let command = app
                .shell()
                .sidecar("douyin-analyst-backend")?
                .env("ANALYST_BACKEND_PORT", port.to_string())
                .env("ANALYST_BACKEND_TOKEN", token.clone())
                .env("ANALYST_DATA_DIR", data_dir.to_string_lossy().to_string());
            let (mut rx, child) = command.spawn()?;

            // Drain the pipe to prevent the child process blocking on a full pipe.
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Terminated(status) => {
                            eprintln!("[sidecar] terminated with code {:?}", status.code);
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
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_request])
        .build(tauri::generate_context!())
        .expect("failed to build Tauri application")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit) {
                stop_backend(app);
            }
        });
}
