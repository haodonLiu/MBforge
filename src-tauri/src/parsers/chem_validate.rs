/// 化学结构验证模块
///
/// 调用 Python sidecar `/api/v1/chem/validate`（RDKit 后端）对 SMILES/E-SMILES
/// 进行结构校验，包括：
/// - RDKit 可解析性
/// - 规范化（canonicalization）
/// - Kekulize / 芳香性检查
/// - 原子数合理性
///
/// 使用路径：Rust → HTTP POST → /api/v1/chem/validate (Python sidecar)

/// 单条验证结果
#[derive(Debug, Clone)]
pub struct ValidateResult {
    pub valid: bool,
    pub canonical_smiles: Option<String>,
    pub issues: Vec<ValidateIssue>,
}

#[derive(Debug, Clone)]
pub struct ValidateIssue {
    pub code: String,
    pub message: String,
    pub severity: String, // "error" | "warning"
}

/// 异步验证单条 E-SMILES
pub async fn validate_smiles(esmiles: &str, sidecar_url: &str) -> Result<ValidateResult, String> {
    let client = crate::core::http::client_30s();
    let url = format!("{}/api/v1/chem/validate", sidecar_url.trim_end_matches('/'));

    let body = serde_json::json!({
        "esmiles": esmiles,
    });

    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Chem validate request failed: {}", e))?;

    let status = resp.status();
    let text = resp
        .text()
        .await
        .map_err(|e| format!("Chem validate read error: {}", e))?;

    if !status.is_success() {
        return Err(format!(
            "Chem validate HTTP {}: {}",
            status,
            &text[..text.floor_char_boundary(200)]
        ));
    }

    let val: serde_json::Value = serde_json::from_str(&text)
        .map_err(|e| format!("Chem validate JSON parse error: {}", e))?;

    let valid = val["valid"].as_bool().unwrap_or(false);
    let canonical = val["canonical_smiles"].as_str().map(|s| s.to_string());

    let issues: Vec<ValidateIssue> = val["issues"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|v| {
                    Some(ValidateIssue {
                        code: v["code"].as_str()?.to_string(),
                        message: v["message"].as_str()?.to_string(),
                        severity: v["severity"].as_str()?.to_string(),
                    })
                })
                .collect()
        })
        .unwrap_or_default();

    Ok(ValidateResult {
        valid,
        canonical_smiles: canonical,
        issues,
    })
}

/// 批量验证（串行，避免并发压垮 RDKit）
pub async fn validate_smiles_batch(
    esmiles_list: &[String],
    sidecar_url: &str,
) -> Vec<(String, ValidateResult)> {
    let mut results = Vec::new();
    for s in esmiles_list {
        match validate_smiles(s, sidecar_url).await {
            Ok(r) => results.push((s.clone(), r)),
            Err(e) => {
                log::warn!("[chem_validate] failed for {}: {}", s, e);
                results.push((
                    s.clone(),
                    ValidateResult {
                        valid: false,
                        canonical_smiles: None,
                        issues: vec![ValidateIssue {
                            code: "VALIDATE_REQUEST_FAILED".into(),
                            message: e,
                            severity: "warning".into(),
                        }],
                    },
                ));
            }
        }
    }
    results
}

/// 净化 E-SMILES：去除空白、E-SMILES 标签等常见 LLM 污染
pub fn sanitize_esmiles(raw: &str) -> String {
    let mut s = raw.trim().to_string();
    // 去除 markdown 代码块标记
    if s.starts_with('`') && s.ends_with('`') {
        s = s.trim_matches('`').to_string();
    }
    // 去除常见的解释性前缀
    for prefix in ["SMILES: ", "E-SMILES: ", "smiles: ", "esmiles: "] {
        if s.starts_with(prefix) {
            s = s[prefix.len()..].to_string();
        }
    }
    s.trim().to_string()
}

/// 安全解析数值（处理 LLM 输出的各种格式问题）
pub fn sanitize_activity_value(raw: &str) -> Option<f64> {
    let cleaned: String = raw
        .chars()
        .filter(|c| c.is_ascii_digit() || *c == '.' || *c == '-' || *c == 'e' || *c == 'E')
        .collect();
    cleaned.parse().ok()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize_esmiles() {
        assert_eq!(sanitize_esmiles("`CCO`"), "CCO");
        assert_eq!(sanitize_esmiles("SMILES: CCO"), "CCO");
        assert_eq!(sanitize_esmiles("  CCO  "), "CCO");
    }

    #[test]
    fn test_sanitize_activity_value() {
        assert_eq!(sanitize_activity_value("5.2 nM"), Some(5.2));
        assert_eq!(sanitize_activity_value("< 10"), Some(10.0));
        assert_eq!(sanitize_activity_value("N/A"), None);
    }
}
