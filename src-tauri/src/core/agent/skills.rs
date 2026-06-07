use std::path::{Path, PathBuf};

use crate::core::config::constants::PROJECT_META_DIR;

const SKILLS_DIR: &str = "skills";

/// 程序性记忆层 — Markdown 格式，人类可读可编辑。
///
/// 参考 Hermes Agent 的 Skills 设计：
/// - 复杂任务完成后自动/手动创建
/// - 独立于结构化记忆（memory.rs），更适合程序性知识
/// - Markdown 格式便于用户直接编辑
pub struct SkillsManager {
    pub(crate) skills_dir: PathBuf,
}

#[derive(Debug, Clone)]
pub struct Skill {
    pub name: String,
    pub content: String,
    pub path: PathBuf,
}

impl SkillsManager {
    pub fn new(project_root: &Path) -> Self {
        let skills_dir = project_root.join(PROJECT_META_DIR).join(SKILLS_DIR);
        let _ = std::fs::create_dir_all(&skills_dir);
        Self { skills_dir }
    }

    /// 获取所有 Skills 列表
    pub fn list(&self) -> Vec<Skill> {
        let mut skills = Vec::new();
        if let Ok(entries) = std::fs::read_dir(&self.skills_dir) {
            for entry in entries.filter_map(|e| e.ok()) {
                let path = entry.path();
                if path.extension().and_then(|e| e.to_str()) == Some("md") {
                    let name = path
                        .file_stem()
                        .and_then(|s| s.to_str())
                        .unwrap_or("unknown")
                        .to_string();
                    let content = std::fs::read_to_string(&path).unwrap_or_default();
                    skills.push(Skill {
                        name,
                        content,
                        path,
                    });
                }
            }
        }
        skills.sort_by(|a, b| a.name.cmp(&b.name));
        skills
    }

    /// 获取单个 Skill
    pub fn get(&self, name: &str) -> Option<Skill> {
        let path = self.skills_dir.join(format!("{}.md", name));
        if path.exists() {
            let content = std::fs::read_to_string(&path).unwrap_or_default();
            Some(Skill {
                name: name.to_string(),
                content,
                path,
            })
        } else {
            None
        }
    }

    /// 保存 Skill（创建或更新）
    pub fn save(&self, name: &str, content: &str) -> Result<(), Box<dyn std::error::Error>> {
        let path = self.skills_dir.join(format!("{}.md", name));
        std::fs::write(&path, content)?;
        Ok(())
    }

    /// 删除 Skill
    pub fn delete(&self, name: &str) -> bool {
        let path = self.skills_dir.join(format!("{}.md", name));
        if path.exists() {
            std::fs::remove_file(&path).is_ok()
        } else {
            false
        }
    }

    /// 搜索 Skills（子串匹配）
    pub fn search(&self, query: &str) -> Vec<Skill> {
        let q = query.to_lowercase();
        self.list()
            .into_iter()
            .filter(|s| s.name.to_lowercase().contains(&q) || s.content.to_lowercase().contains(&q))
            .collect()
    }

    /// 获取所有 Skills 的摘要文本（注入 LLM 上下文用）
    pub fn get_all_summary(&self) -> String {
        let skills = self.list();
        if skills.is_empty() {
            return String::new();
        }
        let mut lines = Vec::new();
        for s in &skills {
            // 截断到 200 字节，使用 safe_truncate 避免在 CJK / emoji 字符中间切
            let preview = if s.content.len() > 200 {
                format!("{}...", crate::core::helpers::safe_truncate(&s.content, 200))
            } else {
                s.content.clone()
            };
            lines.push(format!("[{}] {}", s.name, preview));
        }
        lines.join("\n")
    }

    /// 自动创建 Skill（从对话中提取程序性知识）
    pub fn auto_create_from_conversation(
        &self,
        user_msg: &str,
        assistant_msg: &str,
        sidecar_url: &str,
    ) {
        // 简单启发式：如果对话包含"步骤"、"方法"、"流程"等关键词，可能值得保存
        let keywords = [
            "步骤",
            "方法",
            "流程",
            "教程",
            "如何",
            "怎么做",
            "step",
            "method",
            "how to",
            "workflow",
        ];
        let combined = format!("{} {}", user_msg, assistant_msg).to_lowercase();
        let is_procedural = keywords.iter().any(|k| combined.contains(k));

        if !is_procedural {
            return;
        }

        // 通过 env LLM 直接生成 Skill 内容（不再走 sidecar — sidecar 不再
        // 提供 LLM 端点；LLM 由 Rust 直连 MBFORGE_LLM_* 端点）。
        let prompt = format!(
            "从以下对话中提取程序性知识，生成一个简洁的 Markdown 格式 Skill。\n\
             要求：\n\
             1. 标题用 # 开头\n\
             2. 步骤用数字列表\n\
             3. 关键参数和命令用代码块\n\
             4. 不超过 500 字\n\n\
             用户：{}\n助手：{}",
            user_msg,
            &assistant_msg[..assistant_msg.floor_char_boundary(1000)]
        );

        let _rt = tokio::runtime::Handle::current();
        let skills_dir = self.skills_dir.clone();
        let _ = sidecar_url; // 保留参数位（调用方仍在传），未来可移除
        tokio::spawn(async move {
            let content = match crate::core::agent::llm_client::chat_simple(
                "你是一位知识提取专家。从对话中提取可复用的程序性知识。",
                &prompt,
            )
            .await
            {
                Ok(s) => s,
                Err(e) => {
                    log::warn!("skills extract: LLM call skipped: {e}");
                    return;
                }
            };
            if content.is_empty() {
                return;
            }

            // 用第一行作为 skill 名称
            let name = content
                .lines()
                .next()
                .unwrap_or("unnamed")
                .trim_start_matches('#')
                .trim()
                .chars()
                .take(50)
                .collect::<String>();

            if name.is_empty() {
                return;
            }

            // 清理文件名
            let safe_name = crate::core::helpers::safe_filename(&name);

            let path = skills_dir.join(format!("{}.md", safe_name));
            let _ = std::fs::write(&path, content);
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_skills_manager() {
        let dir = tempfile::tempdir().unwrap();
        let mgr = SkillsManager::new(dir.path());
        mgr.save("test-skill", "# Test\nSteps: 1. Do X\n2. Do Y")
            .unwrap();
        let skills = mgr.list();
        assert_eq!(skills.len(), 1);
        assert_eq!(skills[0].name, "test-skill");
    }

    #[test]
    fn test_search() {
        let dir = tempfile::tempdir().unwrap();
        let mgr = SkillsManager::new(dir.path());
        mgr.save("docking", "# Docking\nRun AutoDock").unwrap();
        mgr.save("filtering", "# Filtering\nUse Lipinski").unwrap();
        let results = mgr.search("dock");
        assert_eq!(results.len(), 1);
    }
}
