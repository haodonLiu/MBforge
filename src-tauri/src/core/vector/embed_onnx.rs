//! ONNX-based embedder — local Qwen3-Embedding-0.6B inference.
//!
//! Replaces the Python sidecar `/api/v1/embed` endpoint with an in-process
//! ONNX Runtime session. CPU-only (0.6B encoder fits comfortably; ~50ms/seq
//! on modern x86). GPU is reserved for MolDet/MolScribe downstream.
//!
//! ## File layout expected on disk
//! `<model_dir>/` is the directory passed to `OnnxEmbedder::load`.
//! - `model.onnx`             — exported encoder (input_ids + attention_mask → last_hidden_state)
//! - `tokenizer.json`         — HuggingFace fast tokenizer
//! - `tokenizer_config.json`  — optional, for `pad_token` / `eos_token` resolution
//!
//! ## Pooling
//! Qwen3-Embedding uses **last-token pooling** with left-padding (the rightmost
//! non-pad position per row, computed as `attention_mask.sum(-1) - 1`).
//! SentenceTransformer-compatible export keeps this responsibility on the caller.
//!
//! ## Matryoshka truncation
//! If `mrl_dim` is set and `< hidden_size`, slice the embedding to the first
//! `mrl_dim` dims and re-normalize.

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};

use ndarray::{Array2, Array3, Axis};
use ort::session::Session;
use ort::value::Tensor;
use tokenizers::Tokenizer;

use super::embedding::EmbedderTrait;

/// Global ONNX model cache, keyed by `model_dir` path.
/// Process-singleton — first load wins, subsequent calls re-use the session.
static MODEL_CACHE: OnceLock<OnnxEmbedder> = OnceLock::new();

/// Embedded state: tokenizer + ort session + dimensions.
pub struct OnnxEmbedder {
    pub tokenizer: Tokenizer,
    pub session: Mutex<Session>,
    /// Inference dtype. Detected from ONNX inputs.
    hidden_size: usize,
    /// Pad token id (resolved from tokenizer config or fallback).
    pad_token_id: i64,
}

impl OnnxEmbedder {
    /// Count tokens for a single text using the model's tokenizer.
    ///
    /// Replaces `helpers::estimate_tokens` (CJK ~1.5/char, ASCII ~0.25/char)
    /// with real BPE counts. Used by `LayeredContext::token_count` to drive
    /// `trim_history` decisions — heuristic estimates mis-sized the
    /// `AGENT_MAX_TOTAL_TOKENS` budget for mixed CJK/ASCII content.
    pub fn count_tokens(&self, text: &str) -> Result<usize, String> {
        let mut tokenizer = self.tokenizer.clone();
        tokenizer
            .with_truncation(Some(tokenizers::TruncationParams {
                max_length: 512,
                ..Default::default()
            }))
            .map_err(|e| format!("tokenizer truncation config: {e}"))?;
        let encoding = tokenizer
            .encode(text, false)
            .map_err(|e| format!("tokenize: {e}"))?;
        Ok(encoding.get_ids().len())
    }

    /// Wrap this embedder as a `TokenCounter` closure. If the tokenizer
    /// call fails, fall back to `crate::core::helpers::estimate_tokens`.
    pub fn as_token_counter(&self) -> crate::core::agent::context::TokenCounter {
        use crate::core::agent::context::TokenCounter;
        use crate::core::helpers::estimate_tokens;
        // `*const OnnxEmbedder` is `!Send + !Sync` by default, so wrap it in
        // a newtype that asserts those bounds. SAFETY: OnnxEmbedder is a
        // process-singleton (`OnceLock`); the pointer is valid for the
        // closure's lifetime.
        struct SendPtr(*const OnnxEmbedder);
        unsafe impl Send for SendPtr {}
        unsafe impl Sync for SendPtr {}
        let ptr = SendPtr(self as *const OnnxEmbedder);
        // Deref to `&OnnxEmbedder` once — `&OnnxEmbedder` is `Send + Sync`
        // because every field inside is. Move that into the closure.
        let embedder: &'static OnnxEmbedder = unsafe { &*ptr.0 };
        Arc::new(move |s: &str| {
            embedder
                .count_tokens(s)
                .unwrap_or_else(|_| estimate_tokens(s))
        })
    }

    /// Load tokenizer + ONNX session from `model_dir`.
    /// Returns the cached singleton if `model_dir` matches the first load.
    pub fn load(model_dir: &Path) -> Result<&'static Self, String> {
        // Fast path: cache hit.
        if let Some(emb) = MODEL_CACHE.get() {
            return Ok(emb);
        }

        let onnx_path = model_dir.join("model.onnx");
        let tok_path = model_dir.join("tokenizer.json");
        if !onnx_path.exists() {
            return Err(format!("ONNX model not found at {}", onnx_path.display()));
        }
        if !tok_path.exists() {
            return Err(format!("tokenizer.json not found at {}", tok_path.display()));
        }

        let tokenizer = Tokenizer::from_file(&tok_path)
            .map_err(|e| format!("tokenizer load failed: {e}"))?;

        // Resolve pad token from tokenizer config; fall back to 0.
        let pad_token_id = read_pad_token_id(model_dir).unwrap_or(0);

        let mut session = Session::builder()
            .map_err(|e| format!("ort Session::builder: {e}"))?
            .with_intra_threads(num_cpus())
            .map_err(|e| format!("ort with_intra_threads: {e}"))?
            .commit_from_file(&onnx_path)
            .map_err(|e| format!("ort commit_from_file: {e}"))?;

        // Probe hidden size by running a single-token forward pass.
        let hidden_size = probe_hidden_size(&mut session, &tokenizer, pad_token_id)?;

        let emb = OnnxEmbedder {
            tokenizer,
            session: Mutex::new(session),
            hidden_size,
            pad_token_id,
        };
        // Race-free install: ignore Err (another thread won the race — use theirs).
        let _ = MODEL_CACHE.set(emb);
        Ok(MODEL_CACHE.get().expect("just set"))
    }

    /// Raw ONNX forward — returns `last_hidden_state` as `[batch, seq, hidden]`.
    fn forward(&self, input_ids: &[Vec<i64>], attention_mask: &[Vec<i64>]) -> Result<Array3<f32>, String> {
        let batch = input_ids.len();
        if batch == 0 {
            return Ok(Array3::zeros((0, 0, self.hidden_size)));
        }
        let seq = input_ids[0].len();
        // Flatten to i64 ndarray [batch, seq].
        let flat: Vec<i64> = input_ids.iter().flatten().copied().collect();
        let ids = Array2::from_shape_vec((batch, seq), flat)
            .map_err(|e| format!("input_ids shape: {e}"))?;
        let mask_flat: Vec<i64> = attention_mask.iter().flatten().copied().collect();
        let mask = Array2::from_shape_vec((batch, seq), mask_flat)
            .map_err(|e| format!("attention_mask shape: {e}"))?;

        let ids_tensor = Tensor::from_array(ids)
            .map_err(|e| format!("ids tensor: {e}"))?;
        let mask_tensor = Tensor::from_array(mask)
            .map_err(|e| format!("mask tensor: {e}"))?;

        let mut session = self.session.lock().map_err(|e| format!("session lock: {e}"))?;
        let outputs = session
            .run(ort::inputs![ids_tensor, mask_tensor])
            .map_err(|e| format!("ort run: {e}"))?;

        // First output is last_hidden_state [batch, seq, hidden].
        let (shape, data) = outputs[0]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("extract last_hidden: {e}"))?;
        let dims: Vec<usize> = shape.iter().map(|&d| d as usize).collect();
        if dims.len() != 3 || dims[0] != batch || dims[1] != seq {
            return Err(format!("unexpected output shape: {:?}", dims));
        }
        let arr = Array3::from_shape_vec((dims[0], dims[1], dims[2]), data.to_vec())
            .map_err(|e| format!("reshape last_hidden: {e}"))?;
        Ok(arr)
    }

    /// Last-token pool + L2 normalize + optional Matryoshka slice.
    ///
    /// Qwen3-Embedding uses left-padding; the last non-pad position per row is
    /// `attention_mask.sum(-1) - 1`.
    pub fn pool_and_normalize(
        &self,
        hidden: &Array3<f32>,
        attention_mask: &[Vec<i64>],
        mrl_dim: Option<usize>,
    ) -> Result<Vec<Vec<f32>>, String> {
        let (batch, _seq, hidden_size) = hidden.dim();
        let target_dim = mrl_dim.unwrap_or(hidden_size).min(hidden_size);

        let mut out = Vec::with_capacity(batch);
        for i in 0..batch {
            let last_idx = (attention_mask[i].iter().sum::<i64>() - 1).max(0) as usize;
            let slice_col = ndarray::Slice::from(last_idx..last_idx + 1);
            let slice_row = ndarray::Slice::from(i..i + 1);
            let row = hidden.slice_axis(Axis(1), slice_col);
            let row = row.slice_axis(Axis(0), slice_row);
            let row = row.remove_axis(Axis(1)).remove_axis(Axis(0));
            // MRL slice.
            let truncated = if target_dim < hidden_size {
                let slice_trunc = ndarray::Slice::from(0..target_dim);
                row.slice_axis(Axis(0), slice_trunc).to_owned()
            } else {
                row.to_owned()
            };
            // L2 normalize.
            let norm = truncated.dot(&truncated).sqrt().max(f32::EPSILON);
            let normalized = truncated / norm;
            out.push(normalized.to_vec());
        }
        Ok(out)
    }
}

impl EmbedderTrait for OnnxEmbedder {
    fn embed(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }

        // Tokenize with left-padding (required for last-token pooling).
        let mut tokenizer = self.tokenizer.clone();
        tokenizer
            .with_padding(Some(tokenizers::PaddingParams {
                strategy: tokenizers::PaddingStrategy::BatchLongest,
                direction: tokenizers::PaddingDirection::Left,
                pad_id: self.pad_token_id as u32,
                pad_token: "<|endoftext|>".to_string(),
                pad_type_id: 0,
                pad_to_multiple_of: None,
            }))
            .with_truncation(Some(tokenizers::TruncationParams {
                max_length: 512,
                ..Default::default()
            }))
            .map_err(|e| format!("tokenizer config: {e}"))?;

        let encodings = tokenizer
            .encode_batch(texts.clone(), true)
            .map_err(|e| format!("tokenize: {e}"))?;

        let input_ids: Vec<Vec<i64>> = encodings
            .iter()
            .map(|e| e.get_ids().iter().map(|&x| x as i64).collect())
            .collect();
        let attention_mask: Vec<Vec<i64>> = encodings
            .iter()
            .map(|e| e.get_attention_mask().iter().map(|&x| x as i64).collect())
            .collect();

        let hidden = self.forward(&input_ids, &attention_mask)?;
        self.pool_and_normalize(&hidden, &attention_mask, None)
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Probe hidden size by running a 2-token forward pass and reading the
/// output shape. Avoids hardcoding the model dim.
fn probe_hidden_size(session: &mut Session, tokenizer: &Tokenizer, pad_token_id: i64) -> Result<usize, String> {
    let mut probe_tok = tokenizer.clone();
    probe_tok
        .with_padding(Some(tokenizers::PaddingParams {
            strategy: tokenizers::PaddingStrategy::BatchLongest,
            direction: tokenizers::PaddingDirection::Left,
            pad_id: pad_token_id as u32,
            pad_token: "<|endoftext|>".to_string(),
            pad_type_id: 0,
            pad_to_multiple_of: None,
        }));
    let enc = probe_tok
        .encode_batch(vec!["ok".to_string()], true)
        .map_err(|e| format!("probe tokenize: {e}"))?;
    let ids: Vec<i64> = enc[0].get_ids().iter().map(|&x| x as i64).collect();
    let mask: Vec<i64> = enc[0].get_attention_mask().iter().map(|&x| x as i64).collect();
    let batch = 1usize;
    let seq = ids.len();
    let ids_arr = Array2::from_shape_vec((batch, seq), ids)
        .map_err(|e| format!("probe shape: {e}"))?;
    let mask_arr = Array2::from_shape_vec((batch, seq), mask)
        .map_err(|e| format!("probe shape: {e}"))?;
    let ids_t = Tensor::from_array(ids_arr).map_err(|e| format!("probe ids: {e}"))?;
    let mask_t = Tensor::from_array(mask_arr).map_err(|e| format!("probe mask: {e}"))?;
    let outputs = session
        .run(ort::inputs![ids_t, mask_t])
        .map_err(|e| format!("probe run: {e}"))?;
    let (shape, _) = outputs[0]
        .try_extract_tensor::<f32>()
        .map_err(|e| format!("probe extract: {e}"))?;
    if shape.len() != 3 {
        return Err(format!("expected 3D output, got {:?}", shape));
    }
    Ok(shape[2] as usize)
}

/// Read `pad_token_id` from `tokenizer_config.json` if present.
fn read_pad_token_id(model_dir: &Path) -> Option<i64> {
    let path = model_dir.join("tokenizer_config.json");
    let bytes = std::fs::read(&path).ok()?;
    let json: serde_json::Value = serde_json::from_slice(&bytes).ok()?;
    json.get("pad_token_id")
        .and_then(|v| v.as_i64())
        .or_else(|| {
            // pad_token is a string — look up its id in the same config.
            let pad_token = json.get("pad_token").and_then(|v| v.as_str())?;
            let added_tokens = json.get("added_tokens_decoder")?.as_object()?;
            for (_k, v) in added_tokens {
                if v.get("content").and_then(|c| c.as_str()) == Some(pad_token) {
                    return v.get("id").and_then(|i| i.as_i64());
                }
            }
            None
        })
}

/// Returns the default ONNX model directory for Qwen3-Embedding-0.6B,
/// resolved through Rust's model cache (same lookup as Python sidecar).
pub fn default_model_dir() -> PathBuf {
    use crate::core::models::resolve::get_model_path;
    if let Some(p) = get_model_path("embedding") {
        return p;
    }
    // Fallback: sidecar-style layout.
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .unwrap_or_else(|_| ".".to_string());
    PathBuf::from(home).join(".cache/mbforge/models/Qwen3-Embedding-0.6B")
}

/// Detect CPU count for `with_intra_threads`. Falls back to 4 on failure.
fn num_cpus() -> usize {
    std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4)
}
