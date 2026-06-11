use std::sync::Arc;
use tauri::State;

use crate::sidecar::SidecarInner;
use crate::core::helpers::LockResultExt;
use crate::core::config::constants::sidecar_url;

#[tauri::command]
pub fn sidecar_status(state: State<Arc<SidecarInner>>) -> serde_json::Value {
    let healthy = state.healthy.load(std::sync::atomic::Ordering::Relaxed);
    let restarts = state
        .restart_count
        .load(std::sync::atomic::Ordering::Relaxed);
    let uptime: u64 = state
        .start_time
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .map(|t: std::time::Instant| t.elapsed().as_secs())
        .unwrap_or(0);
    let state_str = if healthy { "online" } else { "offline" };
    serde_json::json!({
        "healthy": healthy,
        "restartCount": restarts,
        "state": state_str,
        "uptimeSecs": uptime,
        "lastError": *state.last_error.lock().into_inner(),
    })
}

#[tauri::command]
pub fn sidecar_restart(
    state: State<Arc<SidecarInner>>,
    app: tauri::AppHandle,
) -> Result<serde_json::Value, String> {
    crate::sidecar::spawn_and_start_readers(&state, &app)?;
    Ok(serde_json::json!({ "success": true }))
}

/// 探测 Python sidecar 的环境信息（Python 版本、GPU、CUDA、库依赖）。
/// 替代前端的直接 HTTP fallback `fetch('/api/v1/environment/check')`。
#[tauri::command]
pub async fn environment_check() -> Result<serde_json::Value, String> {
    let url = format!("{}/api/v1/environment/check", sidecar_url());
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| format!("reqwest build failed: {e}"))?;
    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("sidecar unreachable: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("sidecar returned HTTP {}", resp.status()));
    }
    resp.json::<serde_json::Value>()
        .await
        .map_err(|e| format!("invalid JSON from sidecar: {e}"))
}
