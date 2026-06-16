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
        allow_patterns: &["*.safetensors", "*.json", "*.txt", "tokenizer*"],
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
        allow_patterns: &["*.safetensors", "*.json", "*.txt", "tokenizer*"],
    },
    ResourceInfo {
        id: "moldet",
        name: "MolDetv2",
        resource_type: ResourceType::Model,
        description: "MolDetv2 分子结构检测 (YOLO, doc + general)",
        size_mb: 11,
        license: "Apache-2.0",
        ms_repo: "UniParser/MolDetv2",
        download_type: "snapshot",
        ms_file: "",
        local_name: "MolDetv2",
        pip_name: "",
        import_name: "",
        allow_patterns: &["*.pt", "*.onnx", "*.json"],
    },
    ResourceInfo {
        id: "molscribe",
        name: "MolScribe",
        resource_type: ResourceType::Model,
        description: "MolScribe 分子图像 → SMILES (Swin-Base 1m680k checkpoint)",
        size_mb: 1134,
        license: "MIT",
        ms_repo: "polyai/MolScribe",
        download_type: "snapshot",
        ms_file: "",
        local_name: "MolScribe",
        pip_name: "",
        import_name: "",
        allow_patterns: &["*.pth", "*.safetensors", "*.json", "*.txt", "tokenizer*", "vocab*"],
    },
    ResourceInfo {
        id: "moldet_coref",
        name: "MolDetect Coref",
        resource_type: ResourceType::Model,
        description: "MolDetect 分子-标号共指消解模型",
        size_mb: 200,
        license: "Apache-2.0",
        ms_repo: "polyai/MolDetect",
        download_type: "snapshot",
        ms_file: "",
        local_name: "MolDetect",
        pip_name: "",
        import_name: "",
        allow_patterns: &["*.ckpt", "*.pt", "*.pth", "*.json", "*.txt"],
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
        allow_patterns: &[],
    },
];
