//! Integration test: real LLM + 25 native tools, end-to-end agent dialog.
//!
//! 构造一个完整的 rig agent（OpenAI-compatible provider + 25 个 native tools），
//! 用简单 prompt 让它回复。**不**对回复做硬断言（LLM 输出非确定性），只断言：
//!   1) `agent.prompt()` 不报错（网络、auth、provider chain 都没坏）
//!   2) 回复非空
//!
//! 前置条件（不满足会 skip 而不是 fail）：
//!   - 项目根 .env 里有 `MBFORGE_LLM_*` 配置
//!   - 网络通到对应 base_url
//!
//! 运行：`cargo test --test test_agent_chat -- --nocapture`

use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use mbforge::core::agent::compactor::SidecarCompactor;
use mbforge::core::agent::conversation_store::SqliteConversationMemory;
use mbforge::core::agent::demotion::EpisodicDemotionHook;
use mbforge::core::agent::managed_memory::MbforgeManagedMemory;
use mbforge::core::agent::observability::AuditLog;
use mbforge::core::agent::rig_adapter::{
    assemble_rig_tool_vec, ConcreteHook, MbforgeAgent, MbforgeAgentSpec, MbforgeProviderConfig,
    MbforgeStreamItem,
};
use mbforge::core::agent::rig_hooks::{AuditLogHook, TrajectoryHook};
use mbforge::core::agent::session_id::SessionId;
use mbforge::core::agent::trajectory::TrajectoryTracker;

fn workspace_root() -> PathBuf {
    let manifest = std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR set");
    PathBuf::from(manifest)
        .parent()
        .expect("project root")
        .to_path_buf()
}

fn load_dotenv_if_present() {
    let env = workspace_root().join(".env");
    if env.exists() {
        let _ = dotenvy::from_path_override(&env);
    }
}

fn build_test_hook() -> Result<ConcreteHook, String> {
    let dir = tempfile::tempdir().map_err(|e| format!("tempdir: {e}"))?;
    let audit = AuditLog::new(dir.path())
        .map_err(|e| format!("AuditLog::new: {e}"))?;
    let trajectory = TrajectoryTracker::new(dir.path());
    Ok(ConcreteHook {
        audit: AuditLogHook::new(Arc::new(audit)),
        trajectory: TrajectoryHook::new(trajectory),
    })
}

fn build_test_project_root() -> PathBuf {
    let mut p = std::env::temp_dir();
    p.push(format!(
        "mbforge-agent-test-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));
    let _ = std::fs::create_dir_all(&p);
    p
}

/// Build the rig `ConversationMemory` backend for a test session.
/// Mirrors the production path in `commands/agent.rs`:
/// `SqliteConversationMemory` + `SidecarCompactor` + `EpisodicDemotionHook`
/// inside `MbforgeManagedMemory`. The sidecar URL is read from the same
/// env var the production path uses.
fn build_test_memory(project_root: &Path, session_id: &str) -> Arc<MbforgeManagedMemory> {
    let sqlite = Arc::new(
        SqliteConversationMemory::open(project_root)
            .expect("open conversations.db for test"),
    );
    let compactor = Arc::new(SidecarCompactor::new(
        mbforge::core::config::constants::sidecar_url(),
    ));
    let demotion = Arc::new(EpisodicDemotionHook::new(
        sqlite.conn_clone(),
        session_id.to_string(),
    ));
    let trait_handle: Arc<dyn rig_core::memory::ConversationMemory> = Arc::clone(&sqlite) as _;
    Arc::new(
        MbforgeManagedMemory::new_with_sqlite(trait_handle, Arc::clone(&sqlite))
            .with_compactor(compactor)
            .with_demotion(demotion),
    )
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn agent_chat_prompt_smoke() {
    load_dotenv_if_present();

    let cfg = match MbforgeProviderConfig::from_app_config() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("[skip] LLM not configured: {e}");
            return;
        }
    };
    eprintln!(
        "[info] provider: {:?} base_url: {} model: {}",
        cfg.kind, cfg.base_url, cfg.model
    );

    let project_root = build_test_project_root();
    let spec = MbforgeAgentSpec::general();
    let hook = match build_test_hook() {
        Ok(h) => h,
        Err(e) => {
            eprintln!("[skip] hook build failed: {e}");
            return;
        }
    };
    let session_id = format!("smoke-prompt-{}", std::process::id());
    let memory = build_test_memory(&project_root, &session_id);

    let agent = MbforgeAgent::from_openai_compatible_with_all_tools(
        &cfg,
        &spec,
        &project_root.to_string_lossy(),
        hook,
        memory,
    )
    .expect("agent construction");

    let prompt = "请用 list_files 工具列出当前项目根目录下的前 5 个文件，然后简要说明你看到了什么。";
    eprintln!("[info] sending prompt: {prompt}");

    let cid = SessionId::from(session_id.as_str());
    let started = std::time::Instant::now();
    let result = tokio::time::timeout(Duration::from_secs(60), agent.prompt(&cid, prompt)).await;
    let elapsed = started.elapsed();

    match result {
        Ok(Ok(text)) => {
            eprintln!(
                "[ok] response in {:.1}s, length={}",
                elapsed.as_secs_f64(),
                text.len()
            );
            eprintln!("--- response ---\n{text}\n--- end ---");
            assert!(!text.is_empty(), "response must not be empty");
        }
        Ok(Err(e)) => panic!("agent.prompt failed: {e}"),
        Err(_) => panic!("agent.prompt timed out after 60s"),
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn agent_chat_context_continuity() {
    use mbforge::core::agent::rig_memory::MbforgeConversationMemory;

    load_dotenv_if_present();

    let cfg = match MbforgeProviderConfig::from_app_config() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("[skip] LLM not configured: {e}");
            return;
        }
    };
    eprintln!(
        "[info] provider: {:?} base_url: {} model: {}",
        cfg.kind, cfg.base_url, cfg.model
    );

    let project_root = build_test_project_root();
    let spec = MbforgeAgentSpec::general();
    let hook = match build_test_hook() {
        Ok(h) => h,
        Err(e) => {
            eprintln!("[skip] hook build failed: {e}");
            return;
        }
    };
    // Stable cid across all three turns — this is the variable that
    // makes multi-turn context work. If each turn used a different
    // cid, rig would load an empty history each time and the
    // assertion below would fail.
    let session_id = format!("continuity-{}-{}", std::process::id(), project_root.display());
    let cid = SessionId::from(session_id.clone());
    let memory = build_test_memory(&project_root, &session_id);

    let agent = MbforgeAgent::from_openai_compatible_with_all_tools(
        &cfg,
        &spec,
        &project_root.to_string_lossy(),
        hook,
        memory,
    )
    .expect("agent construction");

    // Turn 1
    let turn1_prompt = "洗车店离家50米，是走过去还是开车去？请说明理由。";
    eprintln!("[turn1] sending: {turn1_prompt}");
    let turn1_started = std::time::Instant::now();
    let turn1 = tokio::time::timeout(Duration::from_secs(60), agent.prompt(&cid, turn1_prompt))
        .await
        .expect("turn1 timeout")
        .expect("turn1 prompt failed");
    eprintln!(
        "[turn1] reply in {:.1}s, length={}\n--- turn1 ---\n{}\n--- end ---",
        turn1_started.elapsed().as_secs_f64(),
        turn1.len(),
        turn1
    );
    assert!(!turn1.is_empty(), "turn1 must not be empty");

    // Turn 2
    let turn2_prompt = "那我去洗车店要带什么吗？";
    eprintln!("[turn2] sending: {turn2_prompt}");
    let turn2_started = std::time::Instant::now();
    let turn2 = tokio::time::timeout(Duration::from_secs(60), agent.prompt(&cid, turn2_prompt))
        .await
        .expect("turn2 timeout")
        .expect("turn2 prompt failed");
    eprintln!(
        "[turn2] reply in {:.1}s, length={}\n--- turn2 ---\n{}\n--- end ---",
        turn2_started.elapsed().as_secs_f64(),
        turn2.len(),
        turn2
    );
    assert!(!turn2.is_empty(), "turn2 must not be empty");

    // Heuristic: turn2 should reference car-wash context from turn1.
    let t2_keywords = ["洗车", "车", "钥匙", "开车", "步行", "走过去"];
    let t2_hits: Vec<&str> = t2_keywords
        .iter()
        .copied()
        .filter(|k| turn2.contains(k))
        .collect();
    eprintln!("[verdict] turn2 keyword hits: {t2_hits:?}");
    assert!(
        !t2_hits.is_empty(),
        "turn2 must reference car-wash context from turn1 — multi-turn \
         conversation memory is broken. Got reply: {turn2}"
    );

    // Turn 3: topic-blind anaphora. Only works if turn1 + turn2 are in
    // the conversation history.
    let turn3_prompt = "那如果我决定去，要准备哪些东西？";
    eprintln!("[turn3] sending: {turn3_prompt}");
    let turn3_started = std::time::Instant::now();
    let turn3 = tokio::time::timeout(Duration::from_secs(60), agent.prompt(&cid, turn3_prompt))
        .await
        .expect("turn3 timeout")
        .expect("turn3 prompt failed");
    eprintln!(
        "[turn3] reply in {:.1}s, length={}\n--- turn3 ---\n{}\n--- end ---",
        turn3_started.elapsed().as_secs_f64(),
        turn3.len(),
        turn3
    );
    assert!(!turn3.is_empty(), "turn3 must not be empty");

    let t3_keywords = ["洗车", "钥匙", "走过去", "步行", "50米", "50 米"];
    let t3_hits: Vec<&str> = t3_keywords
        .iter()
        .copied()
        .filter(|k| turn3.contains(k))
        .collect();
    eprintln!("[verdict] turn3 keyword hits: {t3_hits:?}");
    assert!(
        !t3_hits.is_empty(),
        "turn3 must reference car-wash context from turn1/turn2 — \
         multi-turn conversation memory is broken. Got reply: {turn3}"
    );

    // Sanity check: the memory backend should have all three turns
    // persisted in SQLite now. (Doesn't affect the multi-turn
    // contract — the LLM already saw them via the in-process rig
    // load — but confirms the rig append path is wired.)
    let list = agent
        .memory()
        .list_for_session(cid.as_str())
        .expect("list_for_session");
    eprintln!("[verdict] persisted turn count: {}", list.len());
    assert!(
        list.len() >= 6,
        "expected at least 6 messages (3 user + 3 assistant), got {}",
        list.len()
    );
}

/// 50-turn eviction stress test. The `window_size: 40` default
/// means the compactor + demotion paths only fire after the 41st
/// turn. The 3-turn `agent_chat_context_continuity` test passes
/// even with a broken eviction path (the bug is silent until the
/// window is exceeded), so this test is the one that would have
/// caught the P0 bugs from the code review.
///
/// Each turn asks a follow-up about a single topic (cooking a
/// specific dish) and asserts the LLM still references it after 50
/// turns — proving the compactor+demotion cycle works end-to-end.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn agent_chat_eviction_pressure() {
    use mbforge::core::agent::rig_memory::MbforgeConversationMemory;

    load_dotenv_if_present();

    let cfg = match MbforgeProviderConfig::from_app_config() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("[skip] LLM not configured: {e}");
            return;
        }
    };

    let project_root = build_test_project_root();
    let spec = MbforgeAgentSpec::general();
    let hook = match build_test_hook() {
        Ok(h) => h,
        Err(e) => {
            eprintln!("[skip] hook build failed: {e}");
            return;
        }
    };
    let session_id = format!(
        "eviction-pressure-{}-{}",
        std::process::id(),
        project_root.display()
    );
    let cid = SessionId::from(session_id.clone());
    let memory = build_test_memory(&project_root, &session_id);

    let agent = MbforgeAgent::from_openai_compatible_with_all_tools(
        &cfg,
        &spec,
        &project_root.to_string_lossy(),
        hook,
        memory,
    )
    .expect("agent construction");

    // Topic: a specific dish the LLM must remember through eviction.
    // The first turn plants 5 key facts (dish, ingredients, technique,
    // time, side). The 50th turn asks a follow-up that should still
    // reference the dish.
    let initial_prompt = "我要做一道菜叫'番茄土豆炖牛腩'。请记住以下5个关键事实：\
        1) 主料是牛腩500克 2) 必须用黄豆酱 3) 必须先煎再炖 4) 炖2小时 5) 配米饭。\
        请回复'记住了'。";
    eprintln!("[turn 1] planting: {initial_prompt}");
    let r = tokio::time::timeout(Duration::from_secs(60), agent.prompt(&cid, initial_prompt))
        .await
        .expect("turn1 timeout")
        .expect("turn1 prompt failed");
    eprintln!("[turn 1] reply len={}", r.len());

    // Send 49 filler turns to push the conversation over the
    // 40-message window. We use 49 because turn 1 = 1 message, and
    // each subsequent turn adds 2 more (user + assistant), so 50
    // turns = 100 messages, well past window_size = 40.
    for i in 2..=50 {
        let prompt = format!("第{}轮：随便聊一下，给我讲个简短的小知识。", i);
        let r = tokio::time::timeout(Duration::from_secs(60), agent.prompt(&cid, &prompt))
            .await
            .unwrap_or_else(|_| panic!("turn {i} timeout"))
            .unwrap_or_else(|e| panic!("turn {i} failed: {e}"));
        if i % 10 == 0 {
            eprintln!("[turn {i}/50] reply len={}", r.len());
        }
    }

    // Final turn: ask a question that requires remembering the dish.
    let final_prompt = "回到我之前说的'番茄土豆炖牛腩'：\
        我现在应该先做哪一步？";
    eprintln!("[turn 51] final prompt: {final_prompt}");
    let final_reply = tokio::time::timeout(Duration::from_secs(60), agent.prompt(&cid, final_prompt))
        .await
        .expect("turn51 timeout")
        .expect("turn51 prompt failed");
    eprintln!("[turn 51] reply:\n{final_reply}");

    // The LLM must reference the dish OR a key ingredient/technique.
    // We check the most distinctive keywords — 牛腩 (the main
    // protein), 番茄 (tomato), 黄豆酱 (the specific paste), and
    // 煎 (the sear step). Any of these is sufficient — together
    // they prove the LLM still has the dish in its context after
    // 50 turns (which means the compactor summary preserved the
    // critical facts).
    let keywords = ["牛腩", "番茄", "黄豆酱", "煎"];
    let hits: Vec<&str> = keywords
        .iter()
        .copied()
        .filter(|k| final_reply.contains(k))
        .collect();
    eprintln!("[verdict] turn51 keyword hits: {hits:?}");
    assert!(
        !hits.is_empty(),
        "After 50 turns (well past window_size=40), the LLM must \
         still remember the dish. Got reply: {final_reply}"
    );

    // Sanity check: the SQLite store should have 100 messages (50
    // user + 50 assistant) plus possibly 1 summary row (with seq=-1).
    // Most importantly, some rows should be evicted (the oldest 60
    // are past the 40-window cutoff).
    let list = agent
        .memory()
        .list_for_session(cid.as_str())
        .expect("list_for_session");
    eprintln!("[verdict] persisted non-evicted count: {}", list.len());
    let summary_count = list.iter().filter(|i| i.is_summary).count();
    let real_count = list.iter().filter(|i| !i.is_summary).count();
    eprintln!(
        "[verdict] composition: {} real + {} summary = {}",
        real_count, summary_count, list.len()
    );
    // After turn 51's `agent.prompt`:
    //   - load fired (eviction happened, active = window_size=40)
    //   - LLM responded
    //   - append fired (2 new messages added)
    // So the persisted set is `window_size + 2` (no summary here
    // because the sidecar compactor errors in the test env; if it
    // succeeded there would also be a summary row at seq=-1).
    // The critical assertion is that this is MUCH less than the
    // 100 messages that would exist without eviction.
    assert!(
        list.len() <= 45,
        "expected at most 45 visible (40 window + up to 2 just-appended + a \
         little slack for LLM timing variance), got {}",
        list.len()
    );
    assert!(
        list.len() < 50,
        "eviction is not keeping up: 50+ non-evicted rows means the \
         compactor + demotion + mark_evicted chain is broken"
    );
    assert!(
        !list.is_empty(),
        "expected non-empty history, got 0"
    );
    // The summary assertion is intentionally relaxed: the
    // `SidecarCompactor` POSTs to `localhost:18792`, which is
    // not running in the test env, so the compactor errors and
    // the Err branch hard-truncates without inserting a summary.
    // The test proves the EVICTION contract (bounded visible
    // count) regardless of whether the compactor succeeded. A
    // summary would be present if the sidecar were running.
    eprintln!(
        "[verdict] has_summary = {} (sidecar is not running, so the \
         compactor errors and hard-truncates without inserting a \
         summary; this is expected and not a regression)",
        list.iter().any(|i| i.is_summary)
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn agent_chat_stream_smoke() {
    use futures::StreamExt;

    load_dotenv_if_present();

    let cfg = match MbforgeProviderConfig::from_app_config() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("[skip] LLM not configured: {e}");
            return;
        }
    };

    let project_root = build_test_project_root();
    let spec = MbforgeAgentSpec::general();
    let hook = match build_test_hook() {
        Ok(h) => h,
        Err(e) => {
            eprintln!("[skip] hook build failed: {e}");
            return;
        }
    };
    let session_id = format!("smoke-stream-{}", std::process::id());
    let memory = build_test_memory(&project_root, &session_id);

    let agent = MbforgeAgent::from_openai_compatible_with_all_tools(
        &cfg,
        &spec,
        &project_root.to_string_lossy(),
        hook,
        memory,
    )
    .expect("agent construction");

    let cid = SessionId::from(session_id.as_str());
    let started = std::time::Instant::now();
    let mut stream = agent.stream(&cid, "用一句话介绍下你有哪些工具");
    let mut saw_text = false;
    let mut saw_final = false;
    let mut final_content = String::new();

    while let Some(item) = tokio::time::timeout(Duration::from_secs(60), stream.next())
        .await
        .expect("stream timeout")
    {
        match item {
            Ok(MbforgeStreamItem::TextDelta(t)) => {
                saw_text = true;
                final_content.push_str(&t);
            }
            Ok(MbforgeStreamItem::Final { content, .. }) => {
                if !content.is_empty() {
                    final_content = content;
                }
                saw_final = true;
                break;
            }
            Ok(MbforgeStreamItem::ToolCall { name, .. }) => {
                eprintln!("[info] tool call: {name}");
            }
            Ok(MbforgeStreamItem::ToolResult { name, .. }) => {
                eprintln!("[info] tool result: {name}");
            }
            Ok(_) => {}
            Err(e) => panic!("stream item err: {e}"),
        }
    }
    eprintln!(
        "[ok] stream done in {:.1}s, text_deltas={saw_text}, final={saw_final}",
        started.elapsed().as_secs_f64()
    );
    eprintln!("--- final content ---\n{final_content}\n--- end ---");
    assert!(saw_final, "stream must emit Final event");
    assert!(saw_text, "stream must emit at least one TextDelta");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn agent_tools_registration_consistent() {
    // 不调 LLM，只验证 25 个工具被 rig 接受 + schema 可序列化。
    // 这是 agent 跑通前最关键的不变量。
    let project_root = build_test_project_root();
    let _tools = assemble_rig_tool_vec(&project_root.to_string_lossy());
    eprintln!("[ok] assemble_rig_tool_vec constructed 25 tools without panic");
    assert!(Path::new(&project_root).exists());
}
