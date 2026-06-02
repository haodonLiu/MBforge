use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::AppHandle;
use tauri::Emitter;

use crate::core::constants::{sidecar_url, DEFAULT_SIDECAR_PORT};

/// 构造 sidecar 日志事件 payload
fn log_event(stream: &str, line: &str) -> serde_json::Value {
    serde_json::json!({
        "stream": stream,
        "line": line,
        "timestamp": chrono::Utc::now().timestamp_millis(),
    })
}

/// Shared state for the Python sidecar process.
pub struct SidecarInner {
    pub child: Mutex<Option<Child>>,
    pub healthy: AtomicBool,
    pub restart_count: AtomicU32,
    pub last_error: Mutex<Option<String>>,
    pub start_time: Mutex<Option<Instant>>,
    pub python: std::path::PathBuf,
    pub resource_dir: std::path::PathBuf,
}

impl SidecarInner {
    pub fn new(python: std::path::PathBuf, resource_dir: std::path::PathBuf) -> Arc<Self> {
        Arc::new(Self {
            child: Mutex::new(None),
            healthy: AtomicBool::new(false),
            restart_count: AtomicU32::new(0),
            last_error: Mutex::new(None),
            start_time: Mutex::new(None),
            python,
            resource_dir,
        })
    }
}

/// Spawn the Python sidecar and start stdout/stderr reader threads.
pub fn spawn_and_start_readers(inner: &Arc<SidecarInner>, app: &AppHandle) -> Result<(), String> {
    // Kill existing child before respawning.
    {
        let mut guard = inner.child.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(ref mut c) = *guard {
            let _ = c.kill();
        }
    }

    let mut cmd = Command::new(&inner.python);
    cmd.arg("-m")
        .arg("uvicorn")
        .arg("mbforge.model_server.main:app")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(DEFAULT_SIDECAR_PORT.to_string())
        .current_dir(&inner.resource_dir)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            let msg = format!("Failed to spawn sidecar: {}", e);
            *inner.last_error.lock().unwrap_or_else(|e| e.into_inner()) = Some(msg.clone());
            return Err(msg);
        }
    };

    {
        let mut guard = inner.child.lock().unwrap_or_else(|e| e.into_inner());
        *guard = Some(child);
    }
    *inner.start_time.lock().unwrap_or_else(|e| e.into_inner()) = Some(Instant::now());

    // --- stdout reader ---
    let app_c = app.clone();
    let inner_c = inner.clone();
    std::thread::spawn(move || {
        let stdout = {
            let mut guard = inner_c.child.lock().unwrap_or_else(|e| e.into_inner());
            guard.as_mut().and_then(|c| c.stdout.take())
        };
        if let Some(stdout) = stdout {
            let reader = BufReader::new(stdout);
            for line in reader.lines().flatten() {
                let _ = app_c.emit("sidecar://log", log_event("stdout", &line));
            }
        }
    });

    // --- stderr reader ---
    let app_c = app.clone();
    let inner_c = inner.clone();
    std::thread::spawn(move || {
        let stderr = {
            let mut guard = inner_c.child.lock().unwrap_or_else(|e| e.into_inner());
            guard.as_mut().and_then(|c| c.stderr.take())
        };
        if let Some(stderr) = stderr {
            let reader = BufReader::new(stderr);
            for line in reader.lines().flatten() {
                let _ = app_c.emit("sidecar://log", log_event("stderr", &line));
            }
        }
    });

    Ok(())
}

fn emit_status(inner: &SidecarInner, app: &AppHandle) {
    let healthy = inner.healthy.load(Ordering::Relaxed);
    let restarts = inner.restart_count.load(Ordering::Relaxed);
    let uptime = inner
        .start_time
        .lock()
        .unwrap()
        .map(|t| t.elapsed().as_secs())
        .unwrap_or(0);
    let state = if healthy { "online" } else { "offline" };
    let payload = serde_json::json!({
        "healthy": healthy,
        "restartCount": restarts,
        "state": state,
        "uptimeSecs": uptime,
        "lastError": *inner.last_error.lock().unwrap_or_else(|e| e.into_inner()),
    });
    let _ = app.emit("sidecar://status", payload);
}

/// Background health-check loop. Auto-restarts sidecar on repeated failures.
pub fn start_health_monitor(inner: Arc<SidecarInner>, app: AppHandle) {
    std::thread::spawn(move || {
        let client = match reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
        {
            Ok(c) => c,
            Err(e) => {
                eprintln!("[sidecar] Failed to create HTTP client: {}", e);
                return;
            }
        };

        // Give the server a few seconds to start before polling.
        std::thread::sleep(Duration::from_secs(3));

        let mut consecutive_failures = 0u32;
        const MAX_FAILURES: u32 = 3;
        const INTERVAL_SECS: u64 = 5;
        const MAX_RESTARTS: u32 = 5;

        loop {
            std::thread::sleep(Duration::from_secs(INTERVAL_SECS));

            let resp = client
                .get(format!("{}/api/v1/health", sidecar_url()))
                .send();

            match resp {
                Ok(r) if r.status().is_success() => {
                    consecutive_failures = 0;
                    let was_healthy = inner.healthy.swap(true, Ordering::Relaxed);
                    if !was_healthy {
                        emit_status(&inner, &app);
                    }
                }
                _ => {
                    consecutive_failures += 1;
                    if consecutive_failures >= MAX_FAILURES {
                        let was_healthy = inner.healthy.swap(false, Ordering::Relaxed);
                        if was_healthy {
                            emit_status(&inner, &app);
                            let restarts =
                                inner.restart_count.fetch_add(1, Ordering::Relaxed);
                            if restarts < MAX_RESTARTS {
                                let _ = app.emit(
                                    "sidecar://log",
                                    serde_json::json!({
                                        "stream": "system",
                                        "line": format!(
                                            "[sidecar] Health check failed {} times. Restarting... ({}/{})",
                                            MAX_FAILURES, restarts + 1, MAX_RESTARTS
                                        ),
                                        "timestamp": chrono::Utc::now().timestamp_millis(),
                                    }),
                                );
                                if let Err(e) = spawn_and_start_readers(&inner, &app) {
                                    *inner.last_error.lock().unwrap_or_else(|e| e.into_inner()) = Some(e.clone());
                                    let _ = app.emit(
                                        "sidecar://log",
                                        serde_json::json!({
                                            "stream": "system",
                                            "line": format!("[sidecar] Restart failed: {}", e),
                                            "timestamp": chrono::Utc::now().timestamp_millis(),
                                        }),
                                    );
                                    emit_status(&inner, &app);
                                } else {
                                    let _ = app.emit(
                                        "sidecar://log",
                                        serde_json::json!({
                                            "stream": "system",
                                            "line": "[sidecar] Sidecar restarted successfully",
                                            "timestamp": chrono::Utc::now().timestamp_millis(),
                                        }),
                                    );
                                }
                            } else {
                                let _ = app.emit(
                                    "sidecar://log",
                                    serde_json::json!({
                                        "stream": "system",
                                        "line": format!(
                                            "[sidecar] Max restarts ({}) reached. Giving up.",
                                            MAX_RESTARTS
                                        ),
                                        "timestamp": chrono::Utc::now().timestamp_millis(),
                                    }),
                                );
                            }
                        }
                    }
                }
            }
        }
    });
}
