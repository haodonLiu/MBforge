/// 全局设置 Tauri 命令（纯 Rust，无 Python sidecar 依赖）
use crate::core::config::AppConfig;

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
    let mut current = serde_json::to_value(&config).map_err(|e| format!("Serialize error: {}", e))?;

    merge_json(&mut current, &settings);

    config = serde_json::from_value(current).map_err(|e| format!("Deserialize error: {}", e))?;
    config.save().map_err(|e| format!("Save config failed: {}", e))
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
