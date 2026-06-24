//! 环境检测 — GPU、Python 版本
use super::catalog::*;
use super::resolve::check_resource;
use crate::config::constants::global_config_dir;

/// 全量环境检查
pub fn check_all() -> EnvironmentReport {
    let python_version = get_python_version();
    let (gpu_available, gpu_name, cuda_version) = detect_gpu();

    let mut resources = Vec::new();
    for info in RESOURCE_CATALOG {
        resources.push(check_resource(info.id));
    }

    let ready = resources
        .iter()
        .filter(|r| r.status == ResourceStatus::Ready)
        .count();
    let total = resources.len();

    EnvironmentReport {
        python_version,
        gpu_available,
        gpu_name,
        cuda_version,
        summary: format!("{}/{} resources ready", ready, total),
        resources,
    }
}

/// 将所有模型路径写入共享 JSON 文件，供 Python sidecar 读取
pub fn write_resolved_paths() {
    use std::io::Write;

    let config_dir = global_config_dir();
    let _ = std::fs::create_dir_all(&config_dir);
    let path = config_dir.join("resolved_paths.json");

    let mut map = serde_json::Map::new();
    for info in RESOURCE_CATALOG {
        if info.resource_type == ResourceType::Model {
            if let Some(p) = super::resolve::get_model_path(info.id) {
                map.insert(
                    info.id.to_string(),
                    serde_json::Value::String(p.to_string_lossy().to_string()),
                );
            }
        }
    }

    let json = serde_json::Value::Object(map);
    if let Ok(mut f) = std::fs::File::create(&path) {
        let _ = f.write_all(
            serde_json::to_string_pretty(&json)
                .unwrap_or_default()
                .as_bytes(),
        );
        log::info!("Wrote resolved model paths to {}", path.display());
    }
}

/// 获取资源目录（纯元数据）
pub fn catalog_json() -> Vec<serde_json::Value> {
    RESOURCE_CATALOG
        .iter()
        .map(|info| {
            serde_json::json!({
                "id": info.id,
                "name": info.name,
                "type": info.resource_type,
                "description": info.description,
                "size_mb": info.size_mb,
                "license": info.license,
                "ms_repo": info.ms_repo,
                "pip_name": info.pip_name,
            })
        })
        .collect()
}

fn get_python_version() -> String {
    let cmd = "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')";
    ["python", "python3"]
        .iter()
        .find_map(|py| {
            std::process::Command::new(py)
                .args(["-c", cmd])
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::null())
                .output()
                .ok()
                .filter(|o| o.status.success())
                .and_then(|o| String::from_utf8(o.stdout).ok())
                .map(|s| s.trim().to_string())
        })
        .unwrap_or_else(|| "unknown".to_string())
}

fn detect_gpu() -> (bool, String, String) {
    let output = std::process::Command::new("nvidia-smi")
        .args(["--query-gpu=name,driver_version", "--format=csv,noheader"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .output();

    match output {
        Ok(out) if out.status.success() => {
            let text = String::from_utf8_lossy(&out.stdout);
            let parts: Vec<&str> = text.trim().split(',').collect();
            let name = parts.first().unwrap_or(&"").trim().to_string();
            let cuda = parts.get(1).unwrap_or(&"").trim().to_string();
            (true, name, cuda)
        }
        _ => (false, String::new(), String::new()),
    }
}
