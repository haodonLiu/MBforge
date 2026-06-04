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

/// 批量验证 — 调用 Python sidecar `/api/v1/chem/validate/batch`
///
/// 相比串行单条调用，减少 N-1 次 HTTP 往返开销。
pub async fn validate_smiles_batch(
    esmiles_list: &[String],
    sidecar_url: &str,
) -> Vec<(String, ValidateResult)> {
    if esmiles_list.is_empty() {
        return Vec::new();
    }

    // 1. 尝试批量端点
    match validate_smiles_batch_api(esmiles_list, sidecar_url).await {
        Ok(results) => return results,
        Err(e) => {
            log::warn!(
                "[chem_validate] Batch endpoint failed (falling back to serial): {}",
                e
            );
        }
    }

    // 2. Fallback: 串行单条调用
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

/// 调用批量验证 API
async fn validate_smiles_batch_api(
    esmiles_list: &[String],
    sidecar_url: &str,
) -> Result<Vec<(String, ValidateResult)>, String> {
    let client = crate::core::http::client_120s();
    let url = format!("{}/api/v1/chem/validate/batch", sidecar_url.trim_end_matches('/'));

    let body = serde_json::json!({
        "esmiles_list": esmiles_list,
    });

    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Batch validate request failed: {}", e))?;

    let status = resp.status();
    let text = resp
        .text()
        .await
        .map_err(|e| format!("Batch validate read error: {}", e))?;

    if !status.is_success() {
        return Err(format!(
            "Batch validate HTTP {}: {}",
            status,
            &text[..text.floor_char_boundary(200)]
        ));
    }

    let val: serde_json::Value = serde_json::from_str(&text)
        .map_err(|e| format!("Batch validate JSON parse error: {}", e))?;

    if !val["success"].as_bool().unwrap_or(false) {
        return Err(format!(
            "Batch validate API error: {}",
            val["error"].as_str().unwrap_or("unknown")
        ));
    }

    let results: Vec<(String, ValidateResult)> = val["results"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|v| {
                    let esmiles = v["esmiles"].as_str()?.to_string();
                    let valid = v["valid"].as_bool().unwrap_or(false);
                    let canonical = v["canonical_smiles"].as_str().map(|s| s.to_string());
                    let issues: Vec<ValidateIssue> = v["issues"]
                        .as_array()
                        .map(|a| {
                            a.iter()
                                .filter_map(|i| {
                                    Some(ValidateIssue {
                                        code: i["code"].as_str()?.to_string(),
                                        message: i["message"].as_str()?.to_string(),
                                        severity: i["severity"].as_str()?.to_string(),
                                    })
                                })
                                .collect()
                        })
                        .unwrap_or_default();
                    Some((
                        esmiles,
                        ValidateResult {
                            valid,
                            canonical_smiles: canonical,
                            issues,
                        },
                    ))
                })
                .collect()
        })
        .unwrap_or_default();

    Ok(results)
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

/// 三层分离：从 E-SMILES 中提取纯净 SMILES + 语义标签
///
/// E-SMILES 格式示例：`<c>1:R1</c>CC(=O)Oc1ccccc1C(=O)O`
/// - 标签: `<c>1:R1</c>` → semantic_tags: {"R1": "Me", ...}
/// - 纯净 SMILES: `CC(=O)Oc1ccccc1C(=O)O`
///
/// 返回 (clean_smiles, original_esmiles, semantic_tags_json)
pub fn separate_esmiles_layers(raw: &str) -> (String, Option<String>, Option<serde_json::Value>) {
    let cleaned = sanitize_esmiles(raw);
    if cleaned.is_empty() {
        return (String::new(), None, None);
    }

    // 检测是否包含 E-SMILES 标签（<c>N:VALUE</c> 或 <TAG>VALUE</TAG> 格式）
    let tag_re = regex::Regex::new(r"<[a-zA-Z]>\d+:[^<]+</[a-zA-Z]>").unwrap();
    let tags: Vec<(String, String)> = tag_re
        .find_iter(&cleaned)
        .filter_map(|m| {
            let tag_str = m.as_str();
            // 解析 <c>1:R1</c> → ("c", "R1") 或更精确地提取编号和值
            let inner = tag_str
                .split('>')
                .nth(1)?
                .split('<')
                .next()?;
            let parts: Vec<&str> = inner.splitn(2, ':').collect();
            if parts.len() == 2 {
                Some((format!("tag_{}", parts[0]), parts[1].to_string()))
            } else {
                None
            }
        })
        .collect();

    // 剥离标签得到纯净 SMILES
    let clean_smiles: String = tag_re.replace_all(&cleaned, "").to_string();
    let clean_smiles = clean_smiles.trim().to_string();

    // 构建 semantic_tags JSON
    let semantic_tags = if tags.is_empty() {
        None
    } else {
        let map: serde_json::Map<String, serde_json::Value> = tags
            .into_iter()
            .map(|(k, v)| (k, serde_json::Value::String(v)))
            .collect();
        Some(serde_json::Value::Object(map))
    };

    // 如果有标签，保留原始 E-SMILES；否则不存
    let esmiles = if semantic_tags.is_some() {
        Some(cleaned)
    } else {
        None
    };

    (clean_smiles, esmiles, semantic_tags)
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
