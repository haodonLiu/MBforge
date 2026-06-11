#![allow(dead_code)]
use serde::{Deserialize, Serialize};

/// 机器可读的错误码，与前端 `ErrorCode` 枚举对齐。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ErrorCode {
    Unknown,
    Network,
    TauriInvoke,
    ApiError,
    SettingsLoad,
    SettingsSave,
    ProjectOpen,
    PdfParse,
    MoleculeSearch,
    ModelNotAvailable,
    NoteNotFound,
    NoteSave,
    NoteDelete,
    FileNotFound,
    FileRead,
    FileWrite,
    FilePermission,
    ProjectCreate,
    ProjectMigrate,
    AgentError,
    KbSearch,
}

impl std::fmt::Display for ErrorCode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ErrorCode::Unknown => write!(f, "UNKNOWN"),
            ErrorCode::Network => write!(f, "NETWORK"),
            ErrorCode::TauriInvoke => write!(f, "TAURI_INVOKE"),
            ErrorCode::ApiError => write!(f, "API_ERROR"),
            ErrorCode::SettingsLoad => write!(f, "SETTINGS_LOAD"),
            ErrorCode::SettingsSave => write!(f, "SETTINGS_SAVE"),
            ErrorCode::ProjectOpen => write!(f, "PROJECT_OPEN"),
            ErrorCode::PdfParse => write!(f, "PDF_PARSE"),
            ErrorCode::MoleculeSearch => write!(f, "MOLECULE_SEARCH"),
            ErrorCode::ModelNotAvailable => write!(f, "MODEL_NOT_AVAILABLE"),
            ErrorCode::NoteNotFound => write!(f, "NOTE_NOT_FOUND"),
            ErrorCode::NoteSave => write!(f, "NOTE_SAVE"),
            ErrorCode::NoteDelete => write!(f, "NOTE_DELETE"),
            ErrorCode::FileNotFound => write!(f, "FILE_NOT_FOUND"),
            ErrorCode::FileRead => write!(f, "FILE_READ"),
            ErrorCode::FileWrite => write!(f, "FILE_WRITE"),
            ErrorCode::FilePermission => write!(f, "FILE_PERMISSION"),
            ErrorCode::ProjectCreate => write!(f, "PROJECT_CREATE"),
            ErrorCode::ProjectMigrate => write!(f, "PROJECT_MIGRATE"),
            ErrorCode::AgentError => write!(f, "AGENT_ERROR"),
            ErrorCode::KbSearch => write!(f, "KB_SEARCH"),
        }
    }
}

/// MBForge 结构化错误类型。
///
/// 内部核心函数统一返回 `Result<T, AppError>`，携带：
/// - `code`：机器可读错误码
/// - `message`：人类可读描述
/// - `path`：可选，涉及的文件路径
/// - `suggestion`：可选，修复建议
///
/// Tauri 命令边界通过 `.map_err(|e| e.to_string())` 转换为字符串。
#[derive(Debug, Clone, Serialize, Deserialize, thiserror::Error)]
#[error("[{code}] {message}{}", path.as_ref().map(|p| format!(" (path: {p})")).unwrap_or_default())]
pub struct AppError {
    pub code: ErrorCode,
    pub message: String,
    pub path: Option<String>,
    pub suggestion: Option<String>,
}

impl AppError {
    pub fn new(code: ErrorCode, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            path: None,
            suggestion: None,
        }
    }

    pub fn with_path(mut self, path: impl Into<String>) -> Self {
        self.path = Some(path.into());
        self
    }

    pub fn with_suggestion(mut self, suggestion: impl Into<String>) -> Self {
        self.suggestion = Some(suggestion.into());
        self
    }
}

/// 从字符串构造 AppError（用于兼容旧代码的快速迁移）。
/// 解析格式 `[ERROR_CODE] message`，无法解析时 fallback 到 Unknown。
impl From<String> for AppError {
    fn from(s: String) -> Self {
        if let Some(captured) = s.strip_prefix('[') {
            if let Some(end) = captured.find(']') {
                let code_str = &captured[..end];
                let message = captured[end + 1..].trim().to_string();
                let code = match code_str {
                    "PROJECT_OPEN" => ErrorCode::ProjectOpen,
                    "PDF_PARSE" => ErrorCode::PdfParse,
                    "MOLECULE_SEARCH" => ErrorCode::MoleculeSearch,
                    "NOTE_NOT_FOUND" => ErrorCode::NoteNotFound,
                    "NOTE_SAVE" => ErrorCode::NoteSave,
                    "NOTE_DELETE" => ErrorCode::NoteDelete,
                    "FILE_NOT_FOUND" => ErrorCode::FileNotFound,
                    "FILE_READ" => ErrorCode::FileRead,
                    "FILE_WRITE" => ErrorCode::FileWrite,
                    "PROJECT_CREATE" => ErrorCode::ProjectCreate,
                    "FILE_PERMISSION" => ErrorCode::FilePermission,
                    "PROJECT_MIGRATE" => ErrorCode::ProjectMigrate,
                    "AGENT_ERROR" => ErrorCode::AgentError,
                    "KB_SEARCH" => ErrorCode::KbSearch,
                    _ => ErrorCode::Unknown,
                };
                return AppError::new(code, message);
            }
        }
        AppError::new(ErrorCode::Unknown, s)
    }
}

impl From<&str> for AppError {
    fn from(s: &str) -> Self {
        AppError::from(s.to_string())
    }
}

/// 便捷类型别名。
pub type AppResult<T> = Result<T, AppError>;

impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self {
        let kind = e.kind();
        let code = match kind {
            std::io::ErrorKind::NotFound => ErrorCode::FileNotFound,
            std::io::ErrorKind::PermissionDenied => ErrorCode::FilePermission,
            _ => ErrorCode::FileRead,
        };
        AppError::new(code, e.to_string())
    }
}

impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self {
        AppError::new(ErrorCode::Unknown, format!("JSON 序列化失败: {e}"))
    }
}

impl From<rusqlite::Error> for AppError {
    fn from(e: rusqlite::Error) -> Self {
        AppError::new(ErrorCode::Unknown, format!("数据库错误: {e}"))
    }
}
