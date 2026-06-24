//! 资源目录 — 所有托管资源的编译期定义
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ResourceType {
    Model,
    PythonPackage,
    Binary,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ResourceStatus {
    Ready,
    NotFound,
    Error,
}

#[derive(Debug, Clone, Serialize)]
pub struct ResourceInfo {
    pub id: &'static str,
    pub name: &'static str,
    #[serde(rename = "type")]
    pub resource_type: ResourceType,
    pub description: &'static str,
    pub size_mb: u64,
    pub license: &'static str,
    pub ms_repo: &'static str,
    pub download_type: &'static str, // "snapshot" | "file"
    pub ms_file: &'static str,       // 单文件下载时的远程文件名
    pub local_name: &'static str,    // 本地文件名/目录名
    pub pip_name: &'static str,      // Python 包名（非空表示需要 pip 安装）
    pub import_name: &'static str,   // Python import 名
    /// snapshot 类型的精确文件路径列表（相对于仓库根）。
    /// 非空时直接下载这些文件，跳过 allow_patterns + API 文件列表拉取。
    /// 支持子目录：`"doc/moldet_v2_yolo11n_960_doc.pt"` 表示 `<dest>/doc/<file>`。
    #[serde(skip)]
    pub files: &'static [&'static str],
    pub allow_patterns: &'static [&'static str], // snapshot 下载时仅匹配的文件模式
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceStatusResult {
    pub id: String,
    pub name: String,
    #[serde(rename = "type")]
    pub resource_type: ResourceType,
    pub status: ResourceStatus,
    pub local_path: String,
    pub size_mb: f64,
    pub version: String,
    pub error: String,
    /// 期望路径：模型应当被检测到的位置（`~/mbforge/models/...`）。Ready 时与 local_path 一致或为子路径，NotFound 时告诉用户应该把文件放在哪里。
    #[serde(default)]
    pub expected_path: String,
    /// 多文件资源（如 MolDetv2 的 doc + general）逐文件状态。前端用于展示子行。
    #[serde(default)]
    pub subfiles: Vec<SubfileStatus>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubfileStatus {
    /// 相对仓库根的路径，如 "doc/moldet_v2_yolo11n_960_doc.pt"
    pub relpath: String,
    /// 友好标签（取第一段目录或文件名），如 "doc"
    pub label: String,
    /// 完整本地路径（不一定存在）
    pub local_path: String,
    /// 是否已下载
    pub ready: bool,
    pub size_mb: f64,
}

impl Default for ResourceStatusResult {
    fn default() -> Self {
        Self {
            id: String::new(),
            name: String::new(),
            resource_type: ResourceType::Model,
            status: ResourceStatus::NotFound,
            local_path: String::new(),
            size_mb: 0.0,
            version: String::new(),
            error: String::new(),
            expected_path: String::new(),
            subfiles: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnvironmentReport {
    pub python_version: String,
    pub gpu_available: bool,
    pub gpu_name: String,
    pub cuda_version: String,
    pub summary: String,
    pub resources: Vec<ResourceStatusResult>,
}

/// 资源目录 — 编译期常量
pub const RESOURCE_CATALOG: &[ResourceInfo] = &[
    // ──── 模型 ────
    ResourceInfo {
        id: "embedding",
        name: "Qwen3-Embedding-0.6B",
        resource_type: ResourceType::Model,
        description: "通义千问3 嵌入模型 (0.6B) — 语义检索",
        size_mb: 1152,
        license: "Apache-2.0",
        ms_repo: "Qwen/Qwen3-Embedding-0.6B",
        download_type: "snapshot",
        ms_file: "",
        local_name: "Qwen3-Embedding-0.6B",
        pip_name: "",
        import_name: "",
        files: &[
            "model.safetensors",
            "config.json",
            "config_sentence_transformers.json",
            "configuration.json",
            "modules.json",
            "1_Pooling/config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json",
            "merges.txt",
        ],
        allow_patterns: &[],
    },
    ResourceInfo {
        id: "reranker",
        name: "Qwen3-Reranker-0.6B",
        resource_type: ResourceType::Model,
        description: "通义千问3 重排序模型 (0.6B) — 结果精排",
        size_mb: 1152,
        license: "Apache-2.0",
        ms_repo: "Qwen/Qwen3-Reranker-0.6B",
        download_type: "snapshot",
        ms_file: "",
        local_name: "Qwen3-Reranker-0.6B",
        pip_name: "",
        import_name: "",
        files: &[
            "model.safetensors",
            "config.json",
            "configuration.json",
            "generation_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json",
            "merges.txt",
        ],
        allow_patterns: &[],
    },
    ResourceInfo {
        id: "moldet",
        name: "MolDetv2",
        resource_type: ResourceType::Model,
        description: "MolDetv2 YOLO 检测 (doc 整页 + general 裁剪)",
        size_mb: 11,
        license: "Apache-2.0",
        ms_repo: "UniParser/MolDetv2",
        download_type: "snapshot",
        ms_file: "",
        local_name: "MolDetv2",
        pip_name: "",
        import_name: "",
        files: &[
            "doc/moldet_v2_yolo11n_960_doc.pt",
            "general/moldet_v2_yolo11n_640_general.pt",
        ],
        allow_patterns: &[],
    },
    ResourceInfo {
        id: "molscribe",
        name: "MolScribe",
        resource_type: ResourceType::Model,
        description: "MolScribe 分子图像 → SMILES (Swin-Base 1m680k checkpoint)",
        size_mb: 432,
        license: "MIT",
        ms_repo: "polyai/MolScribe",
        download_type: "snapshot",
        ms_file: "",
        local_name: "MolScribe",
        pip_name: "",
        import_name: "",
        files: &["swin_base_char_aux_1m680k.pth"],
        allow_patterns: &[],
    },
    // ──── Python 包 ────
    ResourceInfo {
        id: "torch",
        name: "PyTorch",
        resource_type: ResourceType::PythonPackage,
        description: "深度学习框架 (CUDA 12.8)",
        size_mb: 0,
        license: "BSD-3",
        ms_repo: "",
        download_type: "",
        ms_file: "",
        local_name: "",
        pip_name: "torch",
        import_name: "torch",
        files: &[],
        allow_patterns: &[],
    },
    ResourceInfo {
        id: "sentence_transformers",
        name: "Sentence Transformers",
        resource_type: ResourceType::PythonPackage,
        description: "文本嵌入 + CrossEncoder 框架",
        size_mb: 0,
        license: "Apache-2.0",
        ms_repo: "",
        download_type: "",
        ms_file: "",
        local_name: "",
        pip_name: "sentence-transformers",
        import_name: "sentence_transformers",
        files: &[],
        allow_patterns: &[],
    },
    ResourceInfo {
        id: "transformers",
        name: "Transformers",
        resource_type: ResourceType::PythonPackage,
        description: "Hugging Face 模型加载框架",
        size_mb: 0,
        license: "Apache-2.0",
        ms_repo: "",
        download_type: "",
        ms_file: "",
        local_name: "",
        pip_name: "transformers",
        import_name: "transformers",
        files: &[],
        allow_patterns: &[],
    },
    ResourceInfo {
        id: "ultralytics",
        name: "Ultralytics",
        resource_type: ResourceType::PythonPackage,
        description: "YOLO 目标检测框架 (MolDet 依赖)",
        size_mb: 0,
        license: "AGPL-3.0",
        ms_repo: "",
        download_type: "",
        ms_file: "",
        local_name: "",
        pip_name: "ultralytics",
        import_name: "ultralytics",
        files: &[],
        allow_patterns: &[],
    },
];
