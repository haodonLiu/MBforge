/// 全局设置 Tauri 命令（纯 Rust，无 Python sidecar 依赖）
use mbforge_infra::config::AppConfig;
use serde::Serialize;
use std::path::PathBuf;

/// 获取全局设置
#[tauri::command]
pub fn get_settings() -> Result<serde_json::Value, String> {
    let config = AppConfig::load();
    serde_json::to_value(&config).map_err(|e| format!("Serialize config failed: {}", e))
}

/// 保存全局设置
///
/// `settings` 是前端传入的 JSON 对象，只更新非空字段，
/// 其余字段保留原有值。通过递归 JSON merge 实现，
/// 新增字段自动支持，无需手动维护。
#[tauri::command]
pub fn save_settings(settings: serde_json::Value) -> Result<(), String> {
    let mut config = AppConfig::load();
    let mut current =
        serde_json::to_value(&config).map_err(|e| format!("Serialize error: {}", e))?;

    merge_json(&mut current, &settings);

    config = serde_json::from_value(current).map_err(|e| format!("Deserialize error: {}", e))?;
    config
        .save()
        .map_err(|e| format!("Save config failed: {}", e))
}

/// 递归合并 JSON：将 other 中的非 null 值覆盖到 base
fn merge_json(base: &mut serde_json::Value, other: &serde_json::Value) {
    if let (Some(base_obj), Some(other_obj)) = (base.as_object_mut(), other.as_object()) {
        for (key, val) in other_obj {
            if val.is_null() {
                continue;
            }
            if let Some(existing) = base_obj.get_mut(key) {
                if existing.is_object() && val.is_object() {
                    merge_json(existing, val);
                } else {
                    *existing = val.clone();
                }
            } else {
                base_obj.insert(key.clone(), val.clone());
            }
        }
    }
}

// ============================================================================
// About 面板支持：版本信息 / 重置 / 导出 / 打开配置目录
// ============================================================================

/// 构建信息（前端 About 栏目用）
#[derive(Serialize)]
pub struct BuildInfo {
    /// MBForge 应用版本
    pub version: &'static str,
    /// Tauri runtime 版本（编译期固定）
    pub tauri: &'static str,
    /// 操作系统 / 架构
    pub platform: String,
    /// 全局配置文件路径
    pub config_path: String,
}

#[tauri::command]
pub fn app_build_info() -> BuildInfo {
    BuildInfo {
        version: env!("CARGO_PKG_VERSION"),
        tauri: tauri::VERSION,
        platform: format!("{}/{}", std::env::consts::OS, std::env::consts::ARCH),
        config_path: AppConfig::config_path().to_string_lossy().into_owned(),
    }
}

/// 把当前全局配置导出到用户选择的路径（前端用 save dialog 取得 path 后调用）
#[tauri::command]
pub fn export_settings(target_path: String) -> Result<(), String> {
    let config = AppConfig::load();
    let target = PathBuf::from(&target_path);
    if target.as_os_str().is_empty() {
        return Err("Empty target path".into());
    }
    let json =
        serde_json::to_string_pretty(&config).map_err(|e| format!("Serialize failed: {}", e))?;
    std::fs::write(&target, json).map_err(|e| format!("Write {} failed: {}", target.display(), e))
}

/// 重置为默认值
#[tauri::command]
pub fn reset_settings() -> Result<(), String> {
    let config = AppConfig::default();
    config
        .save()
        .map_err(|e| format!("Save default config failed: {}", e))
}

/// 打开配置文件所在目录（前端拿到 path 后调 OS 资源管理器）
#[tauri::command]
pub fn config_dir_path() -> String {
    AppConfig::config_path()
        .parent()
        .map(|p| p.to_string_lossy().into_owned())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn merge_overwrites_llm_fields_with_custom_model_and_url() {
        let mut base = json!({
            "llm": { "provider": "openai_compatible", "base_url": "old", "api_key": "old", "model_name": "default" }
        });
        let incoming = json!({
            "llm": {
                "provider": "anthropic",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test-1234",
                "model_name": "claude-sonnet-4-5",
            }
        });
        merge_json(&mut base, &incoming);
        assert_eq!(base["llm"]["provider"], "anthropic");
        assert_eq!(base["llm"]["base_url"], "https://api.example.com/v1");
        assert_eq!(base["llm"]["api_key"], "sk-test-1234");
        assert_eq!(base["llm"]["model_name"], "claude-sonnet-4-5");
    }

    #[test]
    fn merge_preserves_fields_not_in_incoming() {
        let mut base = json!({
            "llm": { "provider": "openai_compatible", "base_url": "u", "api_key": "k", "model_name": "m" },
            "theme": "dark",
        });
        let incoming = json!({ "llm": { "model_name": "gpt-4o" } });
        merge_json(&mut base, &incoming);
        assert_eq!(base["llm"]["provider"], "openai_compatible");
        assert_eq!(base["llm"]["base_url"], "u");
        assert_eq!(base["llm"]["api_key"], "k");
        assert_eq!(base["llm"]["model_name"], "gpt-4o");
        assert_eq!(base["theme"], "dark");
    }

    #[test]
    fn merge_skips_null_values() {
        // 前端可能把未填字段以 null 形式发出；merge 不应覆盖已有值。
        let mut base = json!({ "llm": { "api_key": "real-key" } });
        let incoming = json!({ "llm": { "api_key": null } });
        merge_json(&mut base, &incoming);
        assert_eq!(base["llm"]["api_key"], "real-key");
    }

    #[test]
    fn merge_supports_new_sections() {
        // 重构后新增了 vlm / ocr / model_server / embed.* / rerank.* 等字段；
        // merge_json 必须能正确处理未在 base 中出现过的节点。
        let mut base = json!({ "theme": "dark" });
        let incoming = json!({
            "vlm": { "provider": "openai_compatible", "model_name": "gpt-4o" },
            "ocr": { "provider": "none", "use_hf_mirror": true },
            "model_server": { "host": "127.0.0.1", "port": 18792, "auto_start": true },
            "embed": { "device": "cuda", "mrl_dim": 1024 },
        });
        merge_json(&mut base, &incoming);
        assert_eq!(base["vlm"]["model_name"], "gpt-4o");
        assert_eq!(base["ocr"]["use_hf_mirror"], true);
        assert_eq!(base["model_server"]["port"], 18792);
        assert_eq!(base["embed"]["device"], "cuda");
        assert_eq!(base["embed"]["mrl_dim"], 1024);
    }
}
