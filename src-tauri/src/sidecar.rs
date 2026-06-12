use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};
use tauri::AppHandle;
use tauri::Emitter;

use crate::core::constants::{
    sidecar_url, DEFAULT_SIDECAR_PORT, EVT_SIDECAR_LOG, EVT_SIDECAR_STATUS,
};
use crate::core::helpers::LockResultExt;

/// 构造 sidecar 日志事件 payload
fn log_event(stream: &str, line: &str) -> serde_json::Value {
    serde_json::json!({
        "stream": stream,
        "line": line,
        "timestamp": chrono::Utc::now().timestamp_millis(),
    })
}

/// 全局共享的 sidecar `Child` 句柄槽 —— `SidecarInner` 和 `ctrlc` handler 都
/// 通过它拿句柄，所以两边操作的是同一个 `Child`（不可能漏 kill）。
///
/// 为什么需要这个：Tauri 的 `app.manage()` 把 `SidecarInner` 塞到 runtime state 里，
/// 但 `ctrlc::set_handler` 回调跑在**任意线程上下文**（不是 Tauri runtime），
/// 不能直接拿 `AppHandle` / `State`。所以这里开一个进程级 `OnceLock<Arc<...>>`，
/// `SidecarInner::new` 调 `child_slot()` 拿同一个 `Arc`，handler 触发时
/// 直接 `child.kill()`。
static SIDECAR_CHILD_SLOT: OnceLock<Arc<Mutex<Option<Child>>>> = OnceLock::new();

pub(crate) fn child_slot() -> &'static Arc<Mutex<Option<Child>>> {
    SIDECAR_CHILD_SLOT.get_or_init(|| Arc::new(Mutex::new(None)))
}

/// 注册 ctrlc handler —— 在 SIGINT/SIGTERM 时 kill sidecar 子进程。
///
/// 必须在 Tauri runtime 起来**之前**调（handler 在进程整个生命周期内有效）。
/// 重复注册会返回 `Err`，所以用 `let _ = ...` 吞掉。
pub fn install_signal_handler() {
    if let Err(e) = ctrlc::set_handler(move || {
        let slot = child_slot();
        let mut guard = match slot.lock() {
            Ok(g) => g,
            Err(p) => p.into_inner(),
        };
        if let Some(child) = guard.as_mut() {
            log::warn!("[sidecar] Caught signal, killing child (pid={:?})", child.id());
            let _ = child.kill();
            let _ = child.wait();
        }
    }) {
        log::warn!("[sidecar] Failed to install ctrlc handler: {}", e);
    }
}

/// Shared state for the Python sidecar process.
pub struct SidecarInner {
    /// 共享 child 句柄 —— 与 `child_slot()` 同一个 `Arc`，让 ctrlc handler 也能 kill
    pub child: Arc<Mutex<Option<Child>>>,
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
            child: child_slot().clone(),
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
        let mut guard = inner.child.lock().into_inner();
        if let Some(ref mut c) = *guard {
            let _ = c.kill();
        }
    }

    let mut cmd = Command::new(&inner.python);
    cmd.arg("-m")
        .arg("uvicorn")
        .arg("mbforge.server:app")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(DEFAULT_SIDECAR_PORT.to_string())
        .current_dir(&inner.resource_dir);

    // 让裸 `python -m uvicorn` 能找到 mbforge 包：
    // - dev:  layout 是 <project_root>/src/mbforge/
    // - prod: layout 是 <resource_dir>/src/mbforge/  （pyproject.toml src 布局）
    // 注入 PYTHONPATH=<resource_dir>/src，覆盖两种 layout
    let src_dir = inner.resource_dir.join("src");
    let existing = std::env::var("PYTHONPATH").unwrap_or_default();
    let new_py_path = if existing.is_empty() {
        src_dir.to_string_lossy().to_string()
    } else {
        format!(
            "{}{}{}",
            src_dir.to_string_lossy(),
            std::path::MAIN_SEPARATOR,
            existing
        )
    };
    cmd.env("PYTHONPATH", new_py_path);

    // 强制 Python 走 UTF-8 编码 —— Windows zh-CN locale 下默认 codepage 是 GBK，
    // 无法编码 ✓ (U+2713) 这类 Unicode 字符，Python 的 logging.StreamHandler
    // 在 stream.write 时会抛 UnicodeEncodeError，lifespan 启动崩溃。
    // 这两个 env var 在 Python 解释器初始化时就读，决定 sys.stdout/stderr 的
    // 编码，比在 Python 端 reconfigure 更可靠（reconfigure 在 Windows pipe 上
    // 可能静默失败）。参考 Python 官方文档 PEP 540 / PYTHONIOENCODING。
    cmd.env("PYTHONIOENCODING", "utf-8");
    cmd.env("PYTHONUTF8", "1");

    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());

    let child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            let msg = format!("Failed to spawn sidecar: {}", e);
            *inner.last_error.lock().into_inner() = Some(msg.clone());
            return Err(msg);
        }
    };

    {
        let mut guard = inner.child.lock().into_inner();
        *guard = Some(child);
    }
    *inner.start_time.lock().into_inner() = Some(Instant::now());

    // --- stdout reader ---
    let app_c = app.clone();
    let inner_c = inner.clone();
    std::thread::spawn(move || {
        let stdout = {
            let mut guard = inner_c.child.lock().into_inner();
            guard.as_mut().and_then(|c| c.stdout.take())
        };
        if let Some(stdout) = stdout {
            let reader = BufReader::new(stdout);
            for line in reader.lines().flatten() {
                let _ = app_c.emit(EVT_SIDECAR_LOG, log_event("stdout", &line));
            }
        }
    });

    // --- stderr reader ---
    let app_c = app.clone();
    let inner_c = inner.clone();
    std::thread::spawn(move || {
        let stderr = {
            let mut guard = inner_c.child.lock().into_inner();
            guard.as_mut().and_then(|c| c.stderr.take())
        };
        if let Some(stderr) = stderr {
            let reader = BufReader::new(stderr);
            for line in reader.lines().flatten() {
                let _ = app_c.emit(EVT_SIDECAR_LOG, log_event("stderr", &line));
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
        .unwrap_or_else(|e| e.into_inner())
        .map(|t| t.elapsed().as_secs())
        .unwrap_or(0);
    let state = if healthy { "online" } else { "offline" };
    let payload = serde_json::json!({
        "healthy": healthy,
        "restartCount": restarts,
        "state": state,
        "uptimeSecs": uptime,
        "lastError": *inner.last_error.lock().into_inner(),
    });
    let _ = app.emit(EVT_SIDECAR_STATUS, payload);
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
                log::error!("[sidecar] Failed to create HTTP client: {}", e);
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
                            let restarts = inner.restart_count.fetch_add(1, Ordering::Relaxed);
                            if restarts < MAX_RESTARTS {
                                let _ = app.emit(
                                    EVT_SIDECAR_LOG,
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
                                    *inner.last_error.lock().into_inner() =
                                        Some(e.clone());
                                    let _ = app.emit(
                                        EVT_SIDECAR_LOG,
                                        serde_json::json!({
                                            "stream": "system",
                                            "line": format!("[sidecar] Restart failed: {}", e),
                                            "timestamp": chrono::Utc::now().timestamp_millis(),
                                        }),
                                    );
                                    emit_status(&inner, &app);
                                } else {
                                    let _ = app.emit(
                                        EVT_SIDECAR_LOG,
                                        serde_json::json!({
                                            "stream": "system",
                                            "line": "[sidecar] Sidecar restarted successfully",
                                            "timestamp": chrono::Utc::now().timestamp_millis(),
                                        }),
                                    );
                                }
                            } else {
                                let _ = app.emit(
                                    EVT_SIDECAR_LOG,
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
