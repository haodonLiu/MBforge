//! 项目笔记 Tauri 命令

use std::path::PathBuf;

use crate::core::helpers::clean_path;
use crate::core::notes::{delete_note, find_backlinks, get_note, list_notes, save_note, Note};

#[tauri::command]
pub fn notes_list(project_root: String) -> Result<Vec<Note>, String> {
    let root = clean_path(&project_root);
    let path = PathBuf::from(&root);
    list_notes(&path)
}

#[tauri::command]
pub fn notes_get(project_root: String, id: String) -> Result<Option<Note>, String> {
    let root = clean_path(&project_root);
    let path = PathBuf::from(&root);
    get_note(&path, &id)
}

#[tauri::command]
pub fn notes_save(project_root: String, note: Note) -> Result<Note, String> {
    let root = clean_path(&project_root);
    let path = PathBuf::from(&root);
    save_note(&path, note)
}

#[tauri::command]
pub fn notes_delete(project_root: String, id: String) -> Result<bool, String> {
    let root = clean_path(&project_root);
    let path = PathBuf::from(&root);
    delete_note(&path, &id)
}

/// 返回引用了目标笔记的其他笔记列表.
///
/// 用于实现 Obsidian 风格的"反向链接"面板.
/// 匹配规则:扫描所有其他笔记的 content,查找 `[[<target_title>]]` 或 `[[<target_title>|alias]]`.
#[tauri::command]
pub fn notes_backlinks(project_root: String, target_id: String) -> Result<Vec<Note>, String> {
    let root = clean_path(&project_root);
    let path = PathBuf::from(&root);
    find_backlinks(&path, &target_id)
}
