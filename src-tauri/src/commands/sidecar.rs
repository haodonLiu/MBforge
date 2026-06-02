use std::sync::Arc;
use tauri::State;

use crate::sidecar::SidecarInner;

#[tauri::command]
pub fn sidecar_status(state: State<Arc<SidecarInner>>) -> serde_json::Value {
    let healthy = state.healthy.load(std::sync::atomic::Ordering::Relaxed);
    let restarts = state
        .restart_count
        .load(std::sync::atomic::Ordering::Relaxed);
    let uptime: u64 = state
        .start_time
        .lock()
        .unwrap()
        .map(|t: std::time::Instant| t.elapsed().as_secs())
        .unwrap_or(0);
    let state_str = if healthy { "online" } else { "offline" };
    serde_json::json!({
        "healthy": healthy,
        "restartCount": restarts,
        "state": state_str,
        "uptimeSecs": uptime,
        "lastError": *state.last_error.lock().unwrap_or_else(|e| e.into_inner()),
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
