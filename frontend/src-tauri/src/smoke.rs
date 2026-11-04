//! Offline desktop integration checks. Always use an isolated data directory.

use serde_json::{json, Value};
use tauri::Manager;
use crate::{BackendState, backend_request, backend_media_url, tokio_sleep};

async fn request(app: &tauri::AppHandle, path: &str, method: &str, body: Option<Value>) -> Result<Value, String> {
    backend_request(app.state::<BackendState>(), path.into(), method.into(), body).await
}

pub async fn run(app: &tauri::AppHandle) -> Result<Value, String> {
    let mut ready = false;
    for _ in 0..120 {
        if request(app, "/api/health", "GET", None).await.is_ok() { ready = true; break; }
        tokio_sleep().await;
    }
    if !ready { return Err("packaged backend did not become ready".into()); }
    if request(app, "/not-allowed", "GET", None).await.is_ok() {
        return Err("proxy accepted an invalid path".into());
    }
    let settings = request(app, "/api/settings", "GET", None).await?;
    if settings.get("OPENAI_API_KEY").is_some() { return Err("settings exposed the API key".into()); }
    let diagnostics = request(app, "/api/diagnostics", "GET", None).await?;
    let asr = request(app, "/api/diagnostics/asr", "GET", None).await?;
    let previous = request(app, "/api/tasks", "GET", None).await?;
    let task = request(app, "/api/tasks", "POST", Some(json!({
        "input_text": "https://www.douyin.com/video/7444000000000012345"
    }))).await?;
    let id = task["id"].as_str().ok_or("task ID missing")?;
    let mut blocked = false;
    for _ in 0..80 {
        let task = request(app, &format!("/api/tasks/{id}"), "GET", None).await?;
        if task["status"] == "blocked" && task["error_code"] == "R0_LIVE_COLLECTION_NOT_VERIFIED" {
            blocked = true;
            break;
        }
        tokio_sleep().await;
    }
    if !blocked { return Err("offline sample was not truthfully blocked".into()); }
    let mut media_range = false;
    if let Ok(video_id) = std::env::var("ANALYST_SMOKE_VIDEO_ID") {
        let url = backend_media_url(app.state::<BackendState>(), video_id)?;
        let response = reqwest::Client::new().get(url).header("Range", "bytes=0-15")
            .send().await.map_err(|e| e.to_string())?;
        if response.status().as_u16() != 206 { return Err("media Range request failed".into()); }
        media_range = response.bytes().await.map_err(|e| e.to_string())?.len() == 16;
        if !media_range { return Err("media Range returned incorrect bytes".into()); }
    }
    let sidecar_pid = app.state::<BackendState>().child.lock().ok()
        .and_then(|child| child.as_ref().map(|child| child.pid()));
    Ok(json!({"ok": true, "type": "OFFLINE_TAURI_SIDECAR_SMOKE",
        "authenticated_proxy": true, "invalid_proxy_path_rejected": true,
        "settings_key_not_exposed": true, "blocked_sample": true,
        "previous_task_count": previous.as_array().map(|tasks| tasks.len()).unwrap_or(0),
        "sidecar_pid": sidecar_pid, "backend_pid": diagnostics["process_id"],
        "bundled_ffmpeg": diagnostics["ffmpeg"], "bundled_ffprobe": diagnostics["ffprobe"],
        "packages": diagnostics["packages"], "synthetic_media_range": media_range,
        "asr_native_libraries_imported": asr["available"], "weights_loaded": asr["weights_loaded"],
        "douyin_live_tested": false, "real_asr_llm_tested": false,
        "webview_playback_tested": false}))
}
