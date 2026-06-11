#![allow(dead_code)]
//! 项目笔记管理 — 存储于 `.mbforge/notes.json`

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

use crate::core::error::{AppError, AppResult, ErrorCode};
use crate::core::helpers::{generate_uuid, now_rfc3339};

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
    root.join(crate::core::config::constants::PROJECT_META_DIR)
        .join("notes.json")
}

fn notes_path_str(root: &Path) -> String {
    notes_path(root).to_string_lossy().to_string()
}

fn load_index(root: &Path) -> AppResult<NotesIndex> {
    let path = notes_path(root);
    if !path.exists() {
        return Ok(NotesIndex::default());
    }
    let content = std::fs::read_to_string(&path)
        .map_err(|e| AppError::new(ErrorCode::FileRead, format!("读取笔记失败: {e}"))
            .with_path(notes_path_str(root)))?;
    serde_json::from_str(&content)
        .map_err(|e| AppError::new(ErrorCode::Unknown, format!("解析笔记失败: {e}"))
            .with_path(notes_path_str(root)))
}

fn save_index(root: &Path, index: &NotesIndex) -> AppResult<()> {
    let path = notes_path(root);
    let content = serde_json::to_string_pretty(index)
        .map_err(|e| AppError::new(ErrorCode::NoteSave, format!("序列化笔记失败: {e}")))?;
    std::fs::write(&path, content)
        .map_err(|e| AppError::new(ErrorCode::NoteSave, format!("保存笔记失败: {e}"))
            .with_path(notes_path_str(root)))
}

pub fn list_notes(root: &Path) -> AppResult<Vec<Note>> {
    let index = load_index(root)?;
    Ok(index.notes)
}

pub fn get_note(root: &Path, id: &str) -> AppResult<Option<Note>> {
    let index = load_index(root)?;
    Ok(index.notes.into_iter().find(|n| n.id == id))
}

pub fn save_note(root: &Path, note: Note) -> AppResult<Note> {
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
    index.notes.into_iter().find(|n| n.id == id)
        .ok_or_else(|| AppError::new(ErrorCode::NoteNotFound, format!("Note {id} saved but not found in index"))
            .with_path(notes_path_str(root)))
}

pub fn delete_note(root: &Path, id: &str) -> AppResult<bool> {
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
pub fn find_backlinks(root: &Path, target_id: &str) -> AppResult<Vec<Note>> {
    let index = load_index(root)?;
    let target = index.notes.iter().find(|n| n.id == target_id);
    let target_title = match target {
        Some(t) => t.title.as_str(),
        None => return Ok(Vec::new()),
    };

    let pattern_title = regex::escape(target_title);
    let re = regex::Regex::new(&format!(r"\[\[\s*{}\s*(\|[^\]]*)?\]\]", pattern_title))
        .map_err(|e| AppError::new(ErrorCode::Unknown, format!("正则构造失败: {e}")))?;

    let backlinks: Vec<Note> = index
        .notes
        .into_iter()
        .filter(|n| n.id != target_id && re.is_match(&n.content))
        .collect();

    Ok(backlinks)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn make_note(id: &str, title: &str, content: &str) -> Note {
        Note {
            id: id.to_string(),
            title: title.to_string(),
            content: content.to_string(),
            tags: Vec::new(),
            links: Vec::new(),
            created_at: "2026-01-01T00:00:00Z".to_string(),
            updated_at: "2026-01-01T00:00:00Z".to_string(),
        }
    }

    fn make_index(notes: Vec<Note>) -> NotesIndex {
        NotesIndex { notes }
    }

    fn write_test_index(dir: &Path, index: &NotesIndex) {
        fs::create_dir_all(dir.join(crate::core::config::constants::PROJECT_META_DIR)).unwrap();
        let path = notes_path(dir);
        let content = serde_json::to_string_pretty(index).unwrap();
        fs::write(&path, content).unwrap();
    }

    #[test]
    fn test_find_backlinks_matches_basic_wikilink() {
        let dir = tempdir();
        let target = make_note("n1", "COX-2 综述", "正文");
        let source1 = make_note("n2", "实验设计", "参考 [[COX-2 综述]] 进行分子对接");
        let source2 = make_note("n3", "合成路线", "无引用");
        let index = make_index(vec![target.clone(), source1.clone(), source2.clone()]);
        write_test_index(&dir, &index);

        let result = find_backlinks(&dir, "n1").unwrap();
        let ids: Vec<&str> = result.iter().map(|n| n.id.as_str()).collect();
        assert_eq!(ids, vec!["n2"], "应只匹配包含 [[COX-2 综述]] 的笔记");
    }

    #[test]
    fn test_find_backlinks_matches_alias_syntax() {
        let dir = tempdir();
        let target = make_note("n1", "Celecoxib", "");
        let source = make_note("n2", "测试", "见 [[Celecoxib|塞来昔布]]");
        write_test_index(&dir, &make_index(vec![target, source]));

        let result = find_backlinks(&dir, "n1").unwrap();
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].id, "n2");
    }

    #[test]
    fn test_find_backlinks_avoids_partial_match() {
        // "AA" 不应误匹配 "[[AAExtra]]"
        let dir = tempdir();
        let target = make_note("n1", "AA", "");
        let decoy = make_note("n2", "陷阱", "见 [[AAExtra]]");
        write_test_index(&dir, &make_index(vec![target, decoy]));

        let result = find_backlinks(&dir, "n1").unwrap();
        assert!(result.is_empty(), "AA 不应匹配 AAExtra");
    }

    #[test]
    fn test_find_backlinks_excludes_self() {
        let dir = tempdir();
        let target = make_note("n1", "自引用", "见 [[自引用]] 的循环引用");
        write_test_index(&dir, &make_index(vec![target]));

        let result = find_backlinks(&dir, "n1").unwrap();
        assert!(result.is_empty(), "笔记不应反向链接自己");
    }

    #[test]
    fn test_find_backlinks_returns_empty_for_missing_target() {
        let dir = tempdir();
        let other = make_note("n1", "其他", "");
        write_test_index(&dir, &make_index(vec![other]));

        let result = find_backlinks(&dir, "nonexistent").unwrap();
        assert!(result.is_empty());
    }

    fn tempdir() -> PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let dir = std::env::temp_dir().join(format!("mbforge_notes_test_{nanos}"));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }
}
