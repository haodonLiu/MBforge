//! 项目笔记管理 — 存储于 `.mbforge/notes.json`

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

use super::helpers::{generate_uuid, now_rfc3339};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NoteLink {
    #[serde(rename = "type")]
    pub note_type: String,
    pub ref_id: String,
    pub ref_title: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Note {
    pub id: String,
    pub title: String,
    pub content: String,
    pub tags: Vec<String>,
    pub links: Vec<NoteLink>,
    pub created_at: String,
    pub updated_at: String,
}

impl Note {
    pub fn new(title: impl Into<String>) -> Self {
        let now = now_rfc3339();
        Self {
            id: generate_uuid(),
            title: title.into(),
            content: String::new(),
            tags: Vec::new(),
            links: Vec::new(),
            created_at: now.clone(),
            updated_at: now,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct NotesIndex {
    notes: Vec<Note>,
}

fn notes_path(root: &Path) -> PathBuf {
    root.join(super::constants::PROJECT_META_DIR).join("notes.json")
}

fn load_index(root: &Path) -> Result<NotesIndex, String> {
    let path = notes_path(root);
    if !path.exists() {
        return Ok(NotesIndex::default());
    }
    let content = std::fs::read_to_string(&path)
        .map_err(|e| format!("读取笔记失败: {e}"))?;
    serde_json::from_str(&content)
        .map_err(|e| format!("解析笔记失败: {e}"))
}

fn save_index(root: &Path, index: &NotesIndex) -> Result<(), String> {
    let path = notes_path(root);
    let content = serde_json::to_string_pretty(index)
        .map_err(|e| format!("序列化笔记失败: {e}"))?;
    std::fs::write(&path, content)
        .map_err(|e| format!("保存笔记失败: {e}"))
}

pub fn list_notes(root: &Path) -> Result<Vec<Note>, String> {
    let index = load_index(root)?;
    Ok(index.notes)
}

pub fn get_note(root: &Path, id: &str) -> Result<Option<Note>, String> {
    let index = load_index(root)?;
    Ok(index.notes.into_iter().find(|n| n.id == id))
}

pub fn save_note(root: &Path, note: Note) -> Result<Note, String> {
    let mut index = load_index(root)?;
    let id = note.id.clone();
    let pos = index.notes.iter().position(|n| n.id == id);
    match pos {
        Some(i) => {
            index.notes[i] = note;
        }
        None => {
            index.notes.push(note);
        }
    }
    save_index(root, &index)?;
    Ok(index.notes.into_iter().find(|n| n.id == id).unwrap())
}

pub fn delete_note(root: &Path, id: &str) -> Result<bool, String> {
    let mut index = load_index(root)?;
    let pos = index.notes.iter().position(|n| n.id == id);
    if let Some(i) = pos {
        index.notes.remove(i);
        save_index(root, &index)?;
        Ok(true)
    } else {
        Ok(false)
    }
}

/// 返回所有"反向引用"目标笔记的其他笔记.
///
/// 通过扫描笔记内容中的 `[[Title]]` 语法匹配.
/// 匹配规则：精确标题匹配,大小写敏感.
///
/// Args:
///     root: 项目根路径
///     target_id: 目标笔记 ID
///
/// Returns:
///     引用了该笔记的其他笔记列表(仅元数据:id/title/updatedAt)
pub fn find_backlinks(root: &Path, target_id: &str) -> Result<Vec<Note>, String> {
    let index = load_index(root)?;
    let target = index.notes.iter().find(|n| n.id == target_id);
    let target_title = match target {
        Some(t) => t.title.as_str(),
        None => return Ok(Vec::new()),
    };

    // 构造 wikilink 模式: [[<title>]]
    // 注意:不能仅匹配 [[<title>],否则 "AA" 会误匹配 "[[AAExtra]]"
    // 安全做法是匹配 [[<title>]] 或 [[<title>|alias]]
    let pattern_title = regex::escape(target_title);
    let re = regex::Regex::new(&format!(
        r"\[\[\s*{}\s*(\|[^\]]*)?\]\]",
        pattern_title
    ))
    .map_err(|e| format!("正则构造失败: {e}"))?;

    let backlinks: Vec<Note> = index
        .notes
        .into_iter()
        .filter(|n| n.id != target_id && re.is_match(&n.content))
        .collect();

    Ok(backlinks)
}