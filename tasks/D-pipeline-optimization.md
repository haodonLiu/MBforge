# Task D: 管线优化

> 难度: ★★★★☆ (Hard)
> 优先级: P0 — 最大的用户体验瓶颈
> 预计工作量: 3-5 天
> 依赖: 无（可立即开始）
> 被依赖: 无

---

## 目标

解决 MBForge 最大的性能瓶颈：27 分钟/文档的管线处理时间。同时集成 MinerU-Popo 图文关联，填补文档解析的最大功能缺口。

---

## 当前瓶颈分析

```
管线总耗时: ~27 分钟/文档（10 节文档，每节 3 批次）

耗时分布:
  Stage 0:   OCR 提取          ~10s    (本地 pdf_inspector)
  Stage 1:   LLM meta 分析     ~5s     (1 次 LLM 调用)
  Stage 2:   逐 Section 提取   ~25min  (10 节 × 3 批次 × (1 调用 + 1 合并) = ~60 次 LLM)
  Stage 3:   合并 + SAR        ~30s    (1 次 LLM 调用)
  Stage 4:   持久化            ~5s     (SQLite + LanceDB 写入)

瓶颈: Stage 2 的 LLM 调用是串行的
```

---

## 设计规范

### 优化 1: LLM 调用并行化

```
当前（串行）:
  Section 1 → batch 1 → LLM → batch 2 → LLM → merge → LLM
  Section 2 → batch 1 → LLM → batch 2 → LLM → merge → LLM
  ...
  Section 10 → ...
  总耗时: Σ(所有 LLM 调用延迟)

目标（并行）:
  ┌─ Section 1 ─┐
  ├─ Section 2 ─┤
  ├─ Section 3 ─┤  ← tokio::JoinAll，并行处理多个 section
  ├─    ...     ├
  └─ Section 10─┘
  每个 section 内部的 batch 仍然串行（有依赖关系）
  总耗时: max(单个 section 耗时) × ceil(10/并发数)
```

**规范**:
- 使用 `tokio::task::JoinSet` 并行处理多个 section
- 默认并发数 = 4（可通过配置调整）
- 每个 section 独立的 TraceContext span
- LLM API 限流保护（避免触发 rate limit）

### 优化 2: 文件缓存命中率提升

```
当前: FileCache 只在 process_document 入口检查
目标: 每个 Stage 的中间结果也缓存

缓存层级:
  L0: 文件级缓存（已有）— mtime+hash → 跳过整个管线
  L1: Stage 1 缓存（新增）— meta 分析结果缓存
  L2: Stage 2 缓存（新增）— 单 section 提取结果缓存
```

**规范**:
- L1/L2 缓存使用 `content_cache.rs` 的已有实现
- 缓存 key: `SHA-256(section_text + prompt_hash)`
- LLM prompt 变化时缓存自动失效

### 优化 3: MinerU-Popo 图文关联集成

```
当前: association.rs 纯文本关联
目标: Popo 结构化图文关联

集成点: pipeline.rs Stage 0.5（OCR 输出后、LLM 处理前）

数据流:
  OCR 输出 (raw text + images)
    → Popo /api/v1/popo/enhance
    → StructuredDocTree + ImageTextAssoc[] + TableFix[]
    → 替代 headings.rs + sections.rs 的启发式逻辑
```

**规范**:
- Popo 作为可选增强层，默认关闭（需要 4B 模型，~8GB VRAM）
- 配置项: `settings.json` 中 `popo.enabled: bool`
- 降级策略: Popo 不可用时回退到现有启发式逻辑
- Python sidecar 新增 `/api/v1/popo/enhance` 端点

---

## 实施步骤

### Step 1: LLM 并行化
- [ ] 分析 `post_process_section()` 的依赖关系
- [ ] 将 `pipeline.rs` Stage 2 的 for 循环改为 `JoinSet`
- [ ] 添加并发限制（semaphore，默认 4）
- [ ] 添加 rate limit 保护（每秒最多 N 次 LLM 调用）
- [ ] 验证：10 section 文档从 25min → ~6min

### Step 2: Stage 级缓存
- [ ] Stage 1 结果缓存（meta 分析）
- [ ] Stage 2 单 section 结果缓存
- [ ] 缓存 key: `SHA-256(text + prompt_version)`
- [ ] 缓存失效: prompt 变化时自动失效

### Step 3: Popo 集成
- [ ] Python sidecar: 新增 `/api/v1/popo/enhance` 端点
- [ ] Rust: `popo_client.rs` — HTTP 客户端
- [ ] Pipeline: Stage 0.5 插入 Popo 调用
- [ ] 配置: `popo.enabled` 开关
- [ ] 降级: Popo 不可用时回退启发式

### Step 4: 提取准确率基准
- [ ] 准备 20 篇真实药物发现 PDF（CN+US 专利）
- [ ] 定义评估指标：分子召回率、活性数据准确率、关联准确率
- [ ] 运行基准测试，记录 baseline
- [ ] 每次优化后对比

---

## 文件范围

| 文件 | 操作 |
|------|------|
| `src-tauri/src/parsers/pipeline.rs` | 修改（并行化 + Popo 集成） |
| `src-tauri/src/parsers/post_process.rs` | 修改（并行 section 处理） |
| `src-tauri/src/parsers/popo_client.rs` | 新建（Popo HTTP 客户端） |
| `src-tauri/src/parsers/association.rs` | 修改（接入 Popo 图文关联） |
| `src-tauri/src/parsers/headings.rs` | 保留（Popo 降级回退） |
| `src-tauri/src/parsers/sections.rs` | 保留（Popo 降级回退） |
| `src/mbforge/model_server/routers/popo.py` | 新建（Popo sidecar 端点） |
| `src/mbforge/model_server/main.py` | 修改（注册 popo router） |

---

## 上下文索引

| 参考 | 位置 | 说明 |
|------|------|------|
| process_document | `src-tauri/src/parsers/pipeline.rs:231` | 管线入口 |
| post_process_section | `src-tauri/src/parsers/post_process.rs:928` | 单 section LLM 调用 |
| classify_and_extract | `src-tauri/src/parsers/pipeline/extract.rs` | Stage 0 |
| headings.rs | `src-tauri/src/parsers/headings.rs` | 启发式标题检测 |
| sections.rs | `src-tauri/src/parsers/sections.rs` | 启发式分块 |
| association.rs | `src-tauri/src/parsers/association.rs` | 纯文本关联 |
| ref/mineru-popo.md | `ref/mineru-popo.md` | Popo 集成方案 |
| ref/wiki-app-notes.md | `ref/wiki-app-notes.md` | Wiki 应用提取管线 |
| ARCHITECTURE.md §五 | `ARCHITECTURE.md` | 管线架构 |
| STANDARDS.md | `tasks/STANDARDS.md` | 开发规范 |
