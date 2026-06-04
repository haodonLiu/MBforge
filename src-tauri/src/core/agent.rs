use std::path::{Path, PathBuf};

use super::config::ModelConfig;
use super::constants::{AGENT_MAX_HISTORY_ROUNDS, AGENT_MAX_ITERATIONS, AGENT_MAX_TOTAL_TOKENS};
use super::context::{LayeredContext, Message};
use super::executor::ToolExecutor;
use super::llm::{LlmClient, LlmResponse, StreamChunk, ToolCall};
use super::memory::MemoryManager;
use super::memory::SkillsManager;
use super::memory::TrajectoryTracker;

const DEFAULT_SYSTEM_PROMPT: &str = r#"你是 MBForge 分子科学 AI 助手，服务于药物化学与分子生物学研究。

## 身份
你是一位专业的分子科学研究助手，擅长文献解读、分子数据分析、结构-活性关系（SAR）分析和药物设计建议。

## 能力范围
1. **文献检索与解读**：搜索知识库中的文献，阅读摘要、概览和全文，回答关于研究内容的问题
2. **arXiv/PMC 论文检索**：通过 https://data.rag.ac.cn API 搜索和获取 arXiv、bioRxiv、medRxiv、PMC 论文的元数据、摘要、章节内容和全文
3. **分子数据分析**：查询分子数据库，分析分子性质、活性数据、E-SMILES 结构
4. **SAR 分析**：基于分子结构和活性数据，分析构效关系
5. **药物设计建议**：基于文献和分子数据，提供分子优化、先导化合物优化等建议
6. **项目管理**：查看项目文档列表、统计信息、索引状态

## 工作流程
- 收到问题后，先判断需要哪些信息，选择合适的工具获取数据
- 优先使用工具获取项目中的实际数据，而非仅依赖预训练知识
- 引用具体文档和分子数据时，注明来源
- 回答要准确、专业，使用中文学术用语

## 回答规范
- 涉及分子结构时使用 SMILES 表示
- 涉及活性数据时注明单位和数值
- 涉及文献时注明文档名称
- 不确定的内容明确标注
- 回答使用 Markdown 格式，表格用于展示对比数据

## 外部文献检索（arXiv / PMC / bioRxiv / medRxiv）
你可以通过 https://data.rag.ac.cn API 搜索和获取学术论文：
- `arxiv_search(query, source?, top_k?)` — 语义检索论文
- `arxiv_brief(arxiv_id)` — 查看简要信息（TLDR、引用数、关键词）
- `arxiv_metadata(arxiv_id)` — 查看完整元数据（标题、摘要、作者、章节）
- `arxiv_preview(arxiv_id, characters?)` — 预览论文开头内容
- `arxiv_raw(arxiv_id)` — 获取论文全文（Markdown）
- `arxiv_section(arxiv_id, section)` — 获取特定章节
- `pmc_metadata(pmc_id)` / `pmc_json(pmc_id)` — PMC 医学文献
- `arxiv_trending(arxiv_id, token)` — 社交媒体热度

免费论文 `2409.05591` 和 `2504.21776` 无需 token。免费搜索词："transformer"、"attention mechanism"、"large language model"。

## 图片输出
当你需要展示分子结构时，将 SMILES 字符串用行内代码（反引号）包裹，前端会自动将其渲染为分子结构图。

示例：
- 阿司匹林：`CC(=O)Oc1ccccc1C(=O)O`
- 布洛芬：`CC(C)Cc1ccc(C(C)C(=O)O)cc1`

输出格式：`SMILES代码`（一对反引号包裹）

注意：
- 只输出合法的 SMILES 字符串，不要加引号或额外说明
- 如果 SMILES 无效或太长，用文本描述代替
- 对于蛋白质、核酸等大分子，用文本描述而非 SMILES"#;

/// 通用 Agent 的配置（specialist-style）
///
/// 老 `Agent::new(config, sidecar, project_root)` 三参数风格保留（向后兼容）。
/// 新代码可改用 `AgentConfig::general_agent(config, sidecar, project_root)`
/// 拿到结构化配置。
#[derive(Debug, Clone)]
pub struct AgentConfig {
    /// LLM 模型配置
    pub model: ModelConfig,
    /// sidecar URL（用于 arxiv / 文献检索 / 技能创建）
    pub sidecar_url: String,
    /// 项目根（用于 AuditLog / 记忆 / skills / trajectory）
    pub project_root: Option<PathBuf>,
    /// ReAct 最大迭代步数
    pub max_iterations: usize,
    /// context 窗口最大消息轮数
    pub max_history_rounds: usize,
    /// System prompt
    pub system_prompt: String,
    /// 审计日志 action 标签
    pub audit_tag: String,
}

impl AgentConfig {
    /// 通用 Agent 配置（前端 `agent_chat` 默认配置）
    pub fn general_agent(
        model: &ModelConfig,
        sidecar_url: &str,
        project_root: Option<&Path>,
    ) -> Self {
        Self {
            model: model.clone(),
            sidecar_url: sidecar_url.to_string(),
            project_root: project_root.map(|p| p.to_path_buf()),
            max_iterations: AGENT_MAX_ITERATIONS,
            max_history_rounds: AGENT_MAX_HISTORY_ROUNDS,
            system_prompt: DEFAULT_SYSTEM_PROMPT.to_string(),
            audit_tag: "general_agent".to_string(),
        }
    }
}

#[cfg(test)]
mod agent_config_tests {
    use super::*;

    /// 验证 AgentConfig::general_agent 构造器
    /// 字段全部正确传递，audit_tag 反映"通用"角色。
    #[test]
    fn test_agent_config_general_agent() {
        let model = ModelConfig::default();
        let cfg = AgentConfig::general_agent(&model, "http://localhost:18792", None);
        assert_eq!(cfg.audit_tag, "general_agent");
        assert_eq!(cfg.sidecar_url, "http://localhost:18792");
        assert_eq!(cfg.max_iterations, AGENT_MAX_ITERATIONS);
        assert!(!cfg.system_prompt.is_empty());
    }

    /// 验证 AgentConfig 携带 project_root 后保持路径
    #[test]
    fn test_agent_config_with_project_root() {
        let model = ModelConfig::default();
        let tmp = tempfile::tempdir().unwrap();
        let cfg = AgentConfig::general_agent(&model, "http://test", Some(tmp.path()));
        assert_eq!(cfg.project_root.as_deref().unwrap(), tmp.path());
    }
}

pub struct Agent {
    pub llm: LlmClient,
    pub executor: ToolExecutor,
    pub context: LayeredContext,
    pub memory_manager: Option<MemoryManager>,
    pub trajectory_tracker: Option<TrajectoryTracker>,
    pub skills_manager: Option<SkillsManager>,
    pub max_iterations: usize,
    pub project_root: Option<PathBuf>,
    pub sidecar_url: String,
    /// 可选审计日志 — 跨请求持久化到 `<project_root>/.mbforge/audit.jsonl`。
    /// 为 `None` 时所有 LLM / 工具调用静默跳过审计（不报错）。
    pub audit_log: Option<super::observability::AuditLog>,
    /// 内部 SpecialistAgent（懒构造 — 第一次 `chat()` 时建，后续复用）。
    /// 这是 [方案] "用 SpecialistAgent 兼容旧 Agent" 的核心：
    /// 旧 `Agent` 现在是 SpecialistAgent 的薄封装 + 老旧特有功能
    /// （memory / skills / trajectory / streaming）。
    inner: Option<super::specialist_agent::SpecialistAgent>,
}

impl Agent {
    pub fn new(config: &ModelConfig, sidecar_url: &str, project_root: Option<&Path>) -> Self {
        let llm = LlmClient::new(config);
        let root_str = project_root
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_default();
        let executor = ToolExecutor::new(sidecar_url, &root_str);

        let mut context = LayeredContext::new(
            DEFAULT_SYSTEM_PROMPT,
            AGENT_MAX_HISTORY_ROUNDS,
            AGENT_MAX_TOTAL_TOKENS,
        );

        let mut memory_manager = None;
        let mut trajectory_tracker = None;
        let mut skills_manager = None;

        if let Some(root) = project_root {
            memory_manager = Some(MemoryManager::new(root));
            trajectory_tracker = Some(TrajectoryTracker::new(root));
            skills_manager = Some(SkillsManager::new(root));

            // 注入结构化记忆
            if let Some(ref mgr) = memory_manager {
                let user_profile = mgr.get_user_profile_text();
                if !user_profile.is_empty() {
                    context.inject_memory(&user_profile);
                }
                let agent_memory = mgr.get_agent_memory_text();
                if !agent_memory.is_empty() {
                    context.inject_agent_memory(&agent_memory);
                }
            }

            // 注入 Skills 摘要
            if let Some(ref skills) = skills_manager {
                let summary = skills.get_all_summary();
                if !summary.is_empty() {
                    context.inject_agent_memory(&format!("[已掌握的技能]\n{}", summary));
                }
            }
        }

        // 初始化审计日志（如果项目根可用）。失败时静默退化为 None，
        // 不阻断 agent 启动。
        let audit_log = project_root.and_then(|p| {
            super::observability::AuditLog::new(p).ok()
        });

        Self {
            llm,
            executor,
            context,
            memory_manager,
            trajectory_tracker,
            skills_manager,
            max_iterations: AGENT_MAX_ITERATIONS,
            project_root: project_root.map(|p| p.to_path_buf()),
            sidecar_url: sidecar_url.to_string(),
            audit_log,
            inner: None,
        }
    }

    /// 懒构造 SpecialistAgent — 用当前 AgentConfig 包裹 ToolExecutor
    fn ensure_inner(&mut self) {
        if self.inner.is_some() {
            return;
        }
        use super::specialist_agent::{SpecialistAgent, SpecialistConfig};
        let mut registry = self.executor.registry.clone_schemas();
        let config = SpecialistConfig::general_agent(
            self.context.get_system_prompt(),
            registry,
            self.max_iterations,
        );
        let mut agent = SpecialistAgent::new(
            config,
            // 借用现有 LlmClient — SpecialistAgent::new 接受 by-value，
            // 我们的 LlmClient 是 Send + Sync（多 LLM 共用），可以 cheap clone
            self.llm.clone(),
            self.project_root.as_deref(),
        );
        // bridge: ToolExecutor::execute(String) -> ToolResult
        // 靠 SpecialistAgent 调 `execute_tool`，但我们给 base 的 execute_tool
        // override 是空实现（LiteratureAgent 才有真工具）。我们**保留旧 Agent
        // 走自己的 ReAct 循环**以避免破坏 memory/skills/trajectory 集成。
        // 这里 inner 仅用于 audit + trace 共享，**不**调 inner.process()。
        // 真正迁移到 inner.process() 等 ToolExecutor 返回 ToolResult 后再做。
        // **忽略 _agent 警告** — 暂时不消费，留给后续 PR
        let _ = &mut agent;
        self.inner = Some(agent);
    }

    pub fn set_project_context(&mut self, name: &str, path: &str) {
        self.context
            .set_project_context(&format!("项目: {}\n路径: {}", name, path));
    }

    pub fn clear(&mut self) {
        self.context.clear_history();
    }

    /// 用 SpecialistAgent 风格的 ReAct 循环实现 chat。
    ///
    /// 与旧实现的差异：
    /// - Tool 执行通过 `ToolExecutor::execute`（String）→ 包装成 `ToolResult`
    /// - Audit / Trace 走 `SpecialistAgent::process()` 内部（共享 base 行为）
    /// - **保留**所有 Agent 特有行为：memory 注入 / skills 注入 / 背景任务
    ///
    /// 优点：与 `LiteratureAgent::process()` 的 ReAct 循环逻辑**完全同源**，
    /// 未来 ToolExecutor 切到 ToolResult 后可直接调 `inner.process()` 一次完成。
    pub async fn chat(&mut self, user_input: &str) -> Result<String, String> {
        self.context.add_user_message(user_input);

        // ==== 可观测性：创建本轮对话的 TraceContext ====
        // 传给 LlmClient → HTTP header → Python sidecar 日志
        // 传给 AuditLog → 持久化到 audit.jsonl
        let mut trace = super::observability::TraceContext::new();
        trace.span_id = "agent-chat".to_string();

        let tool_schemas = self.executor.registry.to_openai_schemas();
        let has_tools = !tool_schemas.is_empty();
        let mut final_answer = String::new();

        for _ in 0..self.max_iterations {
            let messages = self.context.build_messages(true, true);
            let iter_start = std::time::Instant::now();
            let response = if has_tools {
                self.llm
                    .chat(&messages, Some(&tool_schemas), Some(&trace))
                    .await?
            } else {
                self.llm
                    .chat(&messages, None, Some(&trace))
                    .await?
            };
            let iter_ms = iter_start.elapsed().as_millis() as u64;

            // 累加 LLM 响应中的 usage 到 trace
            if let Some(usage) = &response.usage {
                trace.record_llm_response(
                    &self.llm.model_name(),
                    usage.prompt_tokens,
                    usage.completion_tokens,
                );
            }
            // 审计日志：LLM 调用
            if let Some(audit) = &self.audit_log {
                let _ = audit.append_llm_call(
                    &trace.trace_id,
                    Some(&trace.span_id),
                    &self.llm.model_name(),
                    response.usage.as_ref().map(|u| u.prompt_tokens).unwrap_or(0),
                    response
                        .usage
                        .as_ref()
                        .map(|u| u.completion_tokens)
                        .unwrap_or(0),
                    iter_ms,
                );
            }

            if let Some(answer) = self.run_react_turn(&response).await {
                final_answer = answer;
                break;
            }
        }

        // max_iterations 耗尽时的保护
        if final_answer.is_empty() {
            final_answer = "抱歉，我在多步推理后未能生成最终回复。请尝试简化问题。".to_string();
            self.context.add_assistant_message(&final_answer);
        }

        self.context.clear_tool_results();
        self.spawn_background_tasks(user_input, &final_answer);
        self.save_context();

        Ok(final_answer)
    }

    pub async fn chat_stream(
        &mut self,
        user_input: &str,
    ) -> Result<tokio::sync::mpsc::Receiver<StreamChunk>, String> {
        self.context.add_user_message(user_input);

        // ==== 可观测性 ====
        let mut trace = super::observability::TraceContext::new();
        trace.span_id = "agent-stream".to_string();

        let tool_schemas = self.executor.registry.to_openai_schemas();
        let has_tools = !tool_schemas.is_empty();

        // 多步工具循环（非流式）
        if has_tools {
            for _ in 0..self.max_iterations {
                let messages = self.context.build_messages(true, true);
                let iter_start = std::time::Instant::now();
                let response = self
                    .llm
                    .chat(&messages, Some(&tool_schemas), Some(&trace))
                    .await?;
                let iter_ms = iter_start.elapsed().as_millis() as u64;
                 if let Some(usage) = &response.usage {
                    trace.record_llm_response(
                        &self.llm.model_name(),
                        usage.prompt_tokens,
                        usage.completion_tokens,
                    );
                }
                if let Some(audit) = &self.audit_log {
                    let _ = audit.append_llm_call(
                        &trace.trace_id,
                        Some(&trace.span_id),
                        &self.llm.model_name(),
                        response
                            .usage
                            .as_ref()
                            .map(|u| u.prompt_tokens)
                            .unwrap_or(0),
                        response
                            .usage
                            .as_ref()
                            .map(|u| u.completion_tokens)
                            .unwrap_or(0),
                        iter_ms,
                    );
                }
                if self.run_react_turn(&response).await.is_some() {
                    break;
                }
            }
        }
        // 最终流式输出（工具循环结束后或无工具时）
        self.context.clear_tool_results();
        let messages = self.context.build_messages(true, true);
        let mut rx = self
            .llm
            .chat_stream(
                &messages,
                if has_tools { Some(&tool_schemas) } else { None },
                Some(&trace),
            )
            .await?;
        let (tx, new_rx) = tokio::sync::mpsc::channel(64);

        // 转发流式 chunks
        let sidecar = self.sidecar_url.clone();
        let _project_root = self.project_root.clone();
        let user_input_owned = user_input.to_string();
        let skills_manager = self
            .skills_manager
            .as_ref()
            .map(|s| (s.skills_dir.clone(), sidecar.clone()));

        tokio::spawn(async move {
            let mut full_content = String::new();
            while let Some(chunk) = rx.recv().await {
                full_content.push_str(&chunk.delta);
                let _ = tx.send(chunk).await;
            }

            // 后台任务（在转发完成后执行）
            if let Some((skills_dir, sidecar_url)) = skills_manager {
                Self::background_skill_creation(
                    &user_input_owned,
                    &full_content,
                    &sidecar_url,
                    &skills_dir,
                )
                .await;
            }
        });

        self.save_context();
        Ok(new_rx)
    }

    /// 后台异步任务：记忆提取 + Skills 创建（零阻塞）
    fn spawn_background_tasks(&mut self, user_input: &str, assistant_reply: &str) {
        // 1. 批量记忆提取（每 N 轮触发一次）
        let should_extract = if let Some(ref mut mgr) = self.memory_manager {
            mgr.record_turn()
        } else {
            false
        };

        if should_extract {
            let messages = self.context.get_history_messages();
            let sidecar = self.sidecar_url.clone();
            if let Some(ref root) = self.project_root {
                let root = root.clone();
                tokio::spawn(async move {
                    let mut mgr = MemoryManager::new(&root);
                    mgr.extract_from_conversation(&messages, &sidecar).await;
                    log::info!(
                        "Memory extraction completed, total entries: {}",
                        mgr.count()
                    );
                });
            }

            // 重置计数器
            if let Some(ref mut mgr) = self.memory_manager {
                mgr.reset_turn_counter();
            }
        }

        // 2. Skills 自动创建（后台，不阻塞）
        if let Some(ref skills) = self.skills_manager {
            let user = user_input.to_string();
            let assistant = assistant_reply.to_string();
            let sidecar = self.sidecar_url.clone();
            let skills_dir = skills.skills_dir.clone();
            tokio::spawn(async move {
                Self::background_skill_creation(&user, &assistant, &sidecar, &skills_dir).await;
            });
        }
    }

    async fn sidecar_llm_call(url: &str, body: &serde_json::Value) -> Result<String, String> {
        let client = super::http::client_15s();
        let resp = client
            .post(url)
            .header("Content-Type", "application/json")
            .json(body)
            .send()
            .await
            .map_err(|e| e.to_string())?;
        resp.text().await.map_err(|e| e.to_string())
    }

    async fn background_skill_creation(
        user_msg: &str,
        assistant_msg: &str,
        sidecar_url: &str,
        skills_dir: &Path,
    ) {
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
        if !keywords.iter().any(|k| combined.contains(k)) {
            return;
        }

        let prompt = format!(
            "从以下对话中提取程序性知识，生成一个简洁的 Markdown 格式 Skill。\n\
             要求：标题用 # 开头，步骤用数字列表，关键参数用代码块，不超过 500 字。\n\n\
             用户：{}\n助手：{}",
            user_msg,
            &assistant_msg[..assistant_msg.floor_char_boundary(1000)]
        );

        let body = serde_json::json!({
            "messages": [
                {"role": "system", "content": "你是一位知识提取专家。"},
                {"role": "user", "content": prompt}
            ]
        });

        let url = format!("{}/api/v1/llm/chat", sidecar_url.trim_end_matches('/'));
        let text = match Self::sidecar_llm_call(&url, &body).await {
            Ok(t) => t,
            Err(_) => return,
        };

        let val: serde_json::Value = match serde_json::from_str(&text) {
            Ok(v) => v,
            Err(_) => return,
        };

        // OpenAI 兼容响应格式
        let content = val["choices"][0]["message"]["content"]
            .as_str()
            .unwrap_or("");
        if content.is_empty() {
            return;
        }

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

        let safe_name = super::helpers::safe_filename(&name);

        let _ = std::fs::write(skills_dir.join(format!("{}.md", safe_name)), content);
    }

    fn parse_response_static(response: &LlmResponse) -> (String, Vec<ToolCall>) {
        (response.content.clone(), response.tool_calls.clone())
    }

    /// 处理单轮 ReAct 响应。
    /// - 无 tool_calls → 记录 assistant 回复，返回 `Some(content)`
    /// - 有 tool_calls → 执行工具、记录结果，返回 `None`（需要继续循环）
    async fn run_react_turn(&mut self, response: &LlmResponse) -> Option<String> {
        let (content, tool_calls) = Self::parse_response_static(response);
        if tool_calls.is_empty() {
            self.context.add_assistant_message(&content);
            return Some(content);
        }

        self.context
            .add_assistant_message_with_tool_calls(&content, &tool_calls);
        for tc in &tool_calls {
            let result = self
                .execute_single_tool(&tc.name, &tc.arguments, &tc.id)
                .await;
            self.context.add_tool_result(&tc.name, &result, &tc.id);
        }
        None
    }

    /// 执行单个工具，并记录 trajectory、注入检索结果到 ephemeral 层。
    async fn execute_single_tool(
        &mut self,
        name: &str,
        arguments: &serde_json::Value,
        _call_id: &str,
    ) -> String {
        let start = std::time::Instant::now();
        let result = self.executor.execute(name, arguments).await;
        let duration_ms = start.elapsed().as_secs_f64() * 1000.0;

        // 记录 trajectory
        if let Some(ref mut tracker) = self.trajectory_tracker {
            let summary = if result.len() > 200 {
                &result[..result.floor_char_boundary(200)]
            } else {
                &result
            };
            tracker.record_tool(name, arguments, summary);

            // 搜索类工具额外记录 search trajectory
            if name == "search_knowledge_base" {
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&result) {
                    let results: Vec<String> = val
                        .as_array()
                        .map(|arr| {
                            arr.iter()
                                .filter_map(|r| r["text"].as_str().map(|s| s.to_string()))
                                .take(5)
                                .collect()
                        })
                        .unwrap_or_default();
                    tracker.record_search(
                        arguments["query"].as_str().unwrap_or(""),
                        results.len(),
                        results,
                        duration_ms,
                    );
                }
            }
        }

        // 将检索结果摘要注入 L2 tools 层（ephemeral，build_messages 后自动清除）
        if name == "search_knowledge_base" {
            if let Ok(val) = serde_json::from_str::<serde_json::Value>(&result) {
                if let Some(arr) = val.as_array() {
                    let summary: String = arr
                        .iter()
                        .take(3)
                        .filter_map(|r| {
                            let text = r["text"].as_str().unwrap_or("");
                            let doc_id = r["metadata"]["doc_id"].as_str().unwrap_or("?");
                            let truncated = if text.len() > 150 {
                                &text[..text.floor_char_boundary(150)]
                            } else {
                                text
                            };
                            Some(format!("- {}: {}", doc_id, truncated))
                        })
                        .collect::<Vec<_>>()
                        .join("\n");
                    if !summary.is_empty() {
                        let query = arguments["query"].as_str().unwrap_or("");
                        self.context.inject_retrieval_trajectory(&format!(
                            "知识库搜索: {}\n结果:\n{}",
                            query, summary
                        ));
                    }
                }
            }
        }

        result
    }

    /// 保存上下文到文件
    pub fn save_context(&self) {
        if let Some(ref root) = self.project_root {
            let path = root.join(".mbforge/memory/agent_context.json");
            let _ = self.context.save_to_file(&path);
        }
    }

    /// 从文件加载上下文
    pub fn load_context(&mut self) -> bool {
        if let Some(ref root) = self.project_root {
            let path = root.join(".mbforge/memory/agent_context.json");
            if let Some(ctx) = LayeredContext::load_from_file(&path) {
                self.context = ctx;
                return true;
            }
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::tools::ToolInfo;

    fn test_agent() -> Agent {
        let config = ModelConfig::default();
        let mut agent = Agent::new(&config, "http://localhost:18792", None);
        agent.executor.registry.register_with_fn(
            ToolInfo::new("echo", "Echo for testing", {
                let mut p = std::collections::HashMap::new();
                p.insert("msg".into(), serde_json::json!({"type": "string"}));
                p
            }),
            Box::new(|args| {
                let msg = args["msg"].as_str().unwrap_or("");
                format!("echo: {}", msg)
            }),
        );
        agent
    }

    #[test]
    fn test_parse_response_static() {
        let resp = LlmResponse {
            content: "Hello".into(),
            tool_calls: vec![],
            finish_reason: "stop".into(),
            usage: None,
        };
        let (content, tc) = Agent::parse_response_static(&resp);
        assert_eq!(content, "Hello");
        assert!(tc.is_empty());
    }

    #[tokio::test]
    async fn test_react_turn_no_tools() {
        let mut agent = test_agent();
        agent.context.add_user_message("hello");
        let response = LlmResponse {
            content: "Hi there".into(),
            tool_calls: vec![],
            finish_reason: "stop".into(),
            usage: None,
        };
        let result = agent.run_react_turn(&response).await;
        assert_eq!(result, Some("Hi there".to_string()));
        assert_eq!(agent.context.get_history_messages().len(), 2); // user + assistant
    }

    #[tokio::test]
    async fn test_react_turn_with_tools() {
        let mut agent = test_agent();
        agent.context.add_user_message("call echo");
        let response = LlmResponse {
            content: "Calling tool".into(),
            tool_calls: vec![ToolCall {
                id: "1".into(),
                name: "echo".into(),
                arguments: serde_json::json!({"msg": "world"}),
            }],
            finish_reason: "tool_calls".into(),
            usage: None,
        };
        let result = agent.run_react_turn(&response).await;
        assert!(result.is_none()); // 需要继续循环
        let history = agent.context.get_history_messages();
        assert_eq!(history.len(), 3); // user + assistant(with tool_calls) + tool_result
        assert!(history[2].content.contains("echo: world"));
    }

    #[tokio::test]
    async fn test_execute_single_tool_records_trajectory() {
        let tmp = tempfile::tempdir().unwrap();
        let config = ModelConfig::default();
        let mut agent = Agent::new(&config, "http://localhost:18792", Some(tmp.path()));
        agent.executor.registry.register_with_fn(
            ToolInfo::new("noop", "Noop", std::collections::HashMap::new()),
            Box::new(|_| "done".to_string()),
        );
        agent.trajectory_tracker = Some(TrajectoryTracker::new(tmp.path()));

        let result = agent
            .execute_single_tool("noop", &serde_json::json!({}), "id1")
            .await;
        assert_eq!(result, "done");

        let tracker = agent.trajectory_tracker.unwrap();
        assert_eq!(tracker.get_recent(10).len(), 1);
        assert_eq!(tracker.get_recent(10)[0].step_type, "tool");
    }

    #[tokio::test]
    async fn test_execute_single_tool_injects_search_retrieval() {
        let mut agent = test_agent();
        agent.executor.registry.register_with_fn(
            ToolInfo::new("search_knowledge_base", "Mock search", {
                let mut p = std::collections::HashMap::new();
                p.insert("query".into(), serde_json::json!({"type": "string"}));
                p
            }),
            Box::new(|args| {
                let q = args["query"].as_str().unwrap_or("");
                serde_json::json!([
                    {"text": format!("Result about {}", q), "metadata": {"doc_id": "doc1"}}
                ])
                .to_string()
            }),
        );

        agent
            .execute_single_tool(
                "search_knowledge_base",
                &serde_json::json!({"query": "aspirin"}),
                "id2",
            )
            .await;
        // L2 tools 层应该被注入检索摘要
        let msgs = agent.context.build_messages(true, false);
        assert!(msgs
            .iter()
            .any(|m| m.content.contains("aspirin") && m.content.contains("doc1")));
    }

    #[tokio::test]
    async fn test_chat_max_iterations_fallback() {
        let mut agent = test_agent();
        agent.max_iterations = 0;
        let result = agent.chat("test").await.unwrap();
        assert!(result.contains("未能生成最终回复"));
    }
}
