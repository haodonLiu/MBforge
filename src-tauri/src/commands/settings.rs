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
/// 其余字段保留原有值。
#[tauri::command]
pub fn save_settings(settings: serde_json::Value) -> Result<serde_json::Value, String> {
    let mut config = AppConfig::load();

    // 逐层合并：只覆盖前端传入的字段
    if let Some(v) = settings.get("theme").and_then(|v| v.as_str()) {
        config.theme = v.to_string();
    }
    if let Some(v) = settings.get("language").and_then(|v| v.as_str()) {
        config.language = v.to_string();
    }
    if let Some(v) = settings.get("model_cache_dir").and_then(|v| v.as_str()) {
        config.model_cache_dir = v.to_string();
    }

    // llm
    if let Some(llm) = settings.get("llm") {
        if let Some(v) = llm.get("provider").and_then(|v| v.as_str()) {
            config.llm.provider = v.to_string();
        }
        if let Some(v) = llm.get("base_url").and_then(|v| v.as_str()) {
            config.llm.base_url = v.to_string();
        }
        if let Some(v) = llm.get("api_key").and_then(|v| v.as_str()) {
            config.llm.api_key = v.to_string();
        }
        if let Some(v) = llm.get("model_name").and_then(|v| v.as_str()) {
            config.llm.model_name = v.to_string();
        }
        if let Some(v) = llm.get("max_tokens").and_then(|v| v.as_u64()) {
            config.llm.max_tokens = v as u32;
        }
        if let Some(v) = llm.get("temperature").and_then(|v| v.as_f64()) {
            config.llm.temperature = v as f32;
        }
        if let Some(v) = llm.get("top_p").and_then(|v| v.as_f64()) {
            config.llm.top_p = v as f32;
        }
    }

    // embed
    if let Some(embed) = settings.get("embed") {
        if let Some(v) = embed.get("provider").and_then(|v| v.as_str()) {
            config.embed.provider = v.to_string();
        }
        if let Some(v) = embed.get("model_name").and_then(|v| v.as_str()) {
            config.embed.model_name = v.to_string();
        }
        if let Some(v) = embed.get("base_url").and_then(|v| v.as_str()) {
            config.embed.base_url = v.to_string();
        }
        if let Some(v) = embed.get("api_key").and_then(|v| v.as_str()) {
            config.embed.api_key = v.to_string();
        }
        if let Some(v) = embed.get("device").and_then(|v| v.as_str()) {
            config.embed.device = v.to_string();
        }
    }

    // rerank
    if let Some(rerank) = settings.get("rerank") {
        if let Some(v) = rerank.get("provider").and_then(|v| v.as_str()) {
            config.rerank.provider = v.to_string();
        }
        if let Some(v) = rerank.get("model_name").and_then(|v| v.as_str()) {
            config.rerank.model_name = v.to_string();
        }
        if let Some(v) = rerank.get("device").and_then(|v| v.as_str()) {
            config.rerank.device = v.to_string();
        }
        if let Some(v) = rerank.get("max_length").and_then(|v| v.as_u64()) {
            config.rerank.max_length = v as u32;
        }
    }

    // vlm
    if let Some(vlm) = settings.get("vlm") {
        if let Some(v) = vlm.get("provider").and_then(|v| v.as_str()) {
            config.vlm.provider = v.to_string();
        }
        if let Some(v) = vlm.get("base_url").and_then(|v| v.as_str()) {
            config.vlm.base_url = v.to_string();
        }
        if let Some(v) = vlm.get("api_key").and_then(|v| v.as_str()) {
            config.vlm.api_key = v.to_string();
        }
        if let Some(v) = vlm.get("model_name").and_then(|v| v.as_str()) {
            config.vlm.model_name = v.to_string();
        }
    }

    // ocr
    if let Some(ocr) = settings.get("ocr") {
        if let Some(v) = ocr.get("provider").and_then(|v| v.as_str()) {
            config.ocr.provider = v.to_string();
        }
        if let Some(v) = ocr.get("base_url").and_then(|v| v.as_str()) {
            config.ocr.base_url = v.to_string();
        }
        if let Some(v) = ocr.get("api_key").and_then(|v| v.as_str()) {
            config.ocr.api_key = v.to_string();
        }
        if let Some(v) = ocr.get("model_name").and_then(|v| v.as_str()) {
            config.ocr.model_name = v.to_string();
        }
        if let Some(v) = ocr.get("use_hf_mirror").and_then(|v| v.as_bool()) {
            config.ocr.use_hf_mirror = v;
        }
        if let Some(v) = ocr.get("use_pdf_inspector").and_then(|v| v.as_bool()) {
            config.ocr.use_pdf_inspector = v;
        }
    }

    // model_server
    if let Some(ms) = settings.get("model_server") {
        if let Some(v) = ms.get("host").and_then(|v| v.as_str()) {
            config.model_server.host = v.to_string();
        }
        if let Some(v) = ms.get("port").and_then(|v| v.as_u64()) {
            config.model_server.port = v as u16;
        }
        if let Some(v) = ms.get("auto_start").and_then(|v| v.as_bool()) {
            config.model_server.auto_start = v;
        }
        if let Some(v) = ms.get("startup_timeout").and_then(|v| v.as_u64()) {
            config.model_server.startup_timeout = v as u32;
        }
        if let Some(v) = ms.get("health_check_interval").and_then(|v| v.as_u64()) {
            config.model_server.health_check_interval = v as u32;
        }
    }

    config
        .save()
        .map_err(|e| format!("Save config failed: {}", e))?;

    Ok(serde_json::json!({ "success": true }))
}
