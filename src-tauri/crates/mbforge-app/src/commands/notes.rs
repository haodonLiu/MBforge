//! 项目笔记 Tauri 命令

use std::path::PathBuf;

use mbforge_domain::project::notes::{
    delete_note, find_backlinks, get_note, list_notes, save_note, Note,
};
use mbforge_infra::error::{AppError, ErrorCode};
use mbforge_infra::helpers::clean_path;

fn wrap<T>(result: Result<T, AppError>) -> Result<T, String> {
    result.map_err(|e| e.to_string())
}

/// 安全的路径解析，返回清理后的 PathBuf 或 AppError。
fn resolve_path(project_root: &str) -> Result<PathBuf, AppError> {
    let root = clean_path(project_root);
    if root.is_empty() {
        return Err(AppError::new(ErrorCode::ProjectOpen, "项目根路径为空"));
    }
    Ok(PathBuf::from(root))
}

#[tauri::command]
pub fn notes_list(project_root: String) -> Result<Vec<Note>, String> {
    let path = wrap(resolve_path(&project_root))?;
    wrap(list_notes(&path))
}

#[tauri::command]
pub fn notes_get(project_root: String, id: String) -> Result<Option<Note>, String> {
    let path = wrap(resolve_path(&project_root))?;
    wrap(get_note(&path, &id))
}

#[tauri::command]
pub fn notes_save(project_root: String, note: Note) -> Result<Note, String> {
    let path = wrap(resolve_path(&project_root))?;
    wrap(save_note(&path, note))
}

#[tauri::command]
pub fn notes_delete(project_root: String, id: String) -> Result<bool, String> {
    let path = wrap(resolve_path(&project_root))?;
    wrap(delete_note(&path, &id))
}

/// 返回引用了目标笔记的其他笔记列表.
///
/// 用于实现 Obsidian 风格的"反向链接"面板.
#[tauri::command]
pub fn notes_backlinks(project_root: String, target_id: String) -> Result<Vec<Note>, String> {
    let path = wrap(resolve_path(&project_root))?;
    wrap(find_backlinks(&path, &target_id))
}
