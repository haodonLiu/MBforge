# MBForge Master Task Board

> Single source of truth for prioritized work. Replaces the deprecated root
> `TODO.md` (now removed during the 2026-06-29 Rust→Python migration).
>
> Generated from a comment / drift audit of the post-migration codebase.
> If you find a new issue, append it here — not in a side file.

## Legend

| Priority | Meaning | Phase 0 Focus |
|---|---|---|
| P0 | Critical: blocks Phase 0 validation / data trust / user confidence | 工程质量+数据一致性 |
| P1 | High: data quality / extraction accuracy / user experience blockers | 结构化数据准确性 |
| P2 | Medium: code quality, UX polish, doc completeness | 体验优化+文档 |
| P3 | Low: stylistic, future features, nice-to-haves | 暂缓（Phase 1） |

**Phase 0 Roadmap**: 详见 `TODO/PHASE0-ROADMAP.md`（6周计划，2026-07-10 ~ 08-21）

## Snapshot

- **Last drift-sync**: 2026-07-11
- **Phase**: Phase 0 (Research Baseline) — see `TODO/PHASE0-ROADMAP.md`
- **Codebase**: Python-only backend, OpenKB + PageIndex (KB), 19 FastAPI routers, Tauri fully removed
- **Coverage**: Python ~5% (only `tests/unit/parsers/test_coref_alt.py` populated)
- **Tech debt theme**: tests + frontend→backend contract drift; need structured data quality improvements (Activity Extraction, confidence transparency)
- **Priority shift (2026-07-10)**: Evidence Links降级P0→P2; 测试覆盖+数据质量提升为P0
- **Recent work (2026-07-11)**: Evidence-Linked Molecular Infrastructure Phase 1 complete — `evidence` table, `ArtifactResolver`, migration script, frontend `EvidencePanel`

---

## P0 — Critical (Phase 0 Blockers)

**新增（2026-07-10 Phase 0 启动）**:

| ID | Area | Finding | File | Roadmap Week |
|---|---|---|---|---|
| C-6 | Tests | 测试覆盖率 ~5%，pipeline/core/agent 核心模块零测试。阻碍代码重构和功能迭代。目标：≥40% (critical path ≥60%)。 | `tests/` | Week 1-2 |
| C-7 | Pipeline | 阶段失败静默，前端只显示"Unknown error"。需要 StageResult + SSE error events。 | `src/mbforge/pipeline/runner.py`, `frontend/src/components/project/pdf/useIngestPipeline.ts` | Week 1-2 |
| C-8 | Database | Pipeline 中途失败产生脏数据（documents 表有记录但 molecules 表为空）。需要事务边界。 | `src/mbforge/core/database.py`, `src/mbforge/pipeline/runner.py` | Week 1-2 |
| C-9 | Frontend | 分子识别置信度不透明，用户无法判断哪些需要人工校验。需要在 Molecule Library 显示置信度 + 筛选。 | `frontend/src/components/workspace/MoleculeLibrary.tsx` | Week 3 |

**已有（2026-07-07 遗留）**:

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| C-1 | Repo | `ts_errors.txt` (36.6 KB) sits at repo root, not in `.gitignore`. Will be picked up by `git add .` and committed. | `ts_errors.txt` | **RESOLVED 2026-07-07** |
| C-2 | Config | `.gitignore` typo: `.mbforge/` was changed to `.mbccforge/`. Project runtime data would be tracked by git. | `.gitignore` | **RESOLVED 2026-07-07** |
| C-3 | Config | `frontend/tsconfig.json` has the key `"noCheck": true` listed twice (duplicate). TS compiler tolerates it but lint flags it. | `frontend/tsconfig.json` | **OPEN** → Week 6 |
| C-4 | Backend | 首次请求 MolDet/MolScribe 付 5-30s 模型加载成本，无 UX 提示。需要可选预热 + SSE model_loading 事件。 | `src/mbforge/app.py`, `src/mbforge/backends/{moldet,molscribe}.py` | **OPEN** → Week 5 (P2降级) |
| C-5 | Frontend | `frontend/src/api/tauri/_utils.ts` was rewritten to use HTTP, but the directory is still named `api/tauri/`. | `frontend/src/api/tauri/` | **RESOLVED 2026-07-07** |

## P1 — High (Data Quality & Extraction Accuracy)

**新增（2026-07-10 Phase 0 数据质量提升）**:

| ID | Area | Finding | File | Roadmap Week |
|---|---|---|---|---|
| R-10 | Pipeline | 缺少 Activity Data Extraction（IC50/Ki/EC50）。SAR 分析的核心数据缺失，用户仍需手工补充。需新增 `extract_activities.py` + `activities` 表。 | `src/mbforge/pipeline/` | Week 3-4 |
| R-11 | Database | 分子 crop 图片路径（`mol_img_path`）未持久化到数据库，用户无法验证识别是否正确。需补齐 `molecules.crop_path` + 前端展示。 | `src/mbforge/core/database.py`, `frontend/src/components/workspace/MoleculeDetail.tsx` | **RESOLVED 2026-07-11** (Evidence table + ArtifactResolver + EvidencePanel 实现) |
| R-12 | Frontend | Document Viewer 缺失（git status 显示未提交的 `DocumentViewer.tsx`）。用户无法对比 Raw Markdown vs Reorganized，无法验证 LLM 重整质量。 | `frontend/src/components/project/DocumentViewer.tsx` | Week 5 |

**已有（2026-07-07 遗留，合并到 C-6）**:

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| R-1 | Tests | 19 个 routers 无测试覆盖。 | `src/mbforge/routers/*.py` | **合并到 C-6** (Week 1-2 smoke tests) |
| R-2 | Tests | `pipeline/` 模块零测试。 | `src/mbforge/pipeline/` | **合并到 C-6** (Week 1-2) |
| R-3 | Tests | `core/` 模块零测试。 | `src/mbforge/core/` | **合并到 C-6** (Week 1-2) |
| R-4 | Tests | `agent/` 模块零测试。 | `src/mbforge/agent/` | **降级到 P2** (Phase 0 暂不扩展 agent) |
| R-5 | Frontend | SSE 客户端无重连逻辑。 | `frontend/src/api/sse.ts` | **降级到 P2** (需前端架构改造) |
| R-6 | Frontend | `httpFetch` 错误映射不完整。 | `frontend/src/api/http/_utils.ts` | **合并到 C-7** (Week 1-2 错误处理) |
| R-7 | Backend | `backends/qwen3.py` docstring 过时。 | `src/mbforge/backends/qwen3.py` | **RESOLVED 2026-07-07** |
| R-8 | Backend | `resource_manager.py` 的 `nvidia-smi` 阻塞调用。 | `src/mbforge/core/resource_manager.py` | **降级到 P3** (非 Phase 0 性能瓶颈) |
| R-9 | Docs | `CLAUDE.md` 引用 `archived/` 路径。 | `CLAUDE.md` | **RESOLVED 2026-07-05** |

## P2 — Medium (UX Polish & Documentation)

**新增（2026-07-10 Phase 0 体验优化）**:

| ID | Area | Finding | File | Roadmap Week |
|---|---|---|---|---|
| D-9 | Frontend | Pipeline 执行 5-10 分钟，前端只有 spinner，不知道卡在哪个阶段。需要进度可视化（9 阶段进度条 + 预估剩余时间）。 | `frontend/src/components/project/pdf/PdfPipelineFlow.tsx` | Week 5 |
| D-10 | Frontend | Settings 页面的 OCR 配置和 Model Management 不完整。需要 Provider 优先级排序 + Clear Cache 功能。 | `frontend/src/components/settings/PdfParseSection.tsx`, `src/mbforge/routers/settings.py` | Week 6 |
| D-11 | Docs | README.md 过度承诺"AI co-pilot"能力，与 Phase 0 定位（research baseline）不符。需要大幅修订，明确 85-90% 准确率 + 需人工校验。 | `README.md` | Week 6 |
| D-12 | Docs | 缺少 CONTRIBUTING.md 和 Issue 模板，外部贡献者无法快速上手。需补齐开发环境指南 + bug/accuracy report 模板。 | `CONTRIBUTING.md`, `.github/ISSUE_TEMPLATE/` | Week 6 |

**已有（2026-07-07 遗留）**:

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| D-1 | Tests | `tests/unit/test_pipeline.py`, `tests/unit/test_embed_rerank.py`, `tests/unit/test_zvec_service.py`, `tests/unit/test_agent.py`, `tests/unit/parsers/test_molecule_parsers.py`, `tests/integration/test_real_pdfs.py` referenced in prior `TODO/INDEX.md` no longer exist. Either re-create or update references. | `TODO/INDEX.md:60` (history) | **RESOLVED 2026-07-07** (`test_embed_rerank.py`, `test_zvec_service.py` confirmed deleted; remaining tests present and passing) |
| D-2 | Python | `backends/moldet.py` switched to `moldet_v2_yolo26n_960_doc.pt` with conf_threshold 0.5 but no test asserts the new defaults. | `src/mbforge/backends/moldet.py` | **OPEN** |
| D-3 | Python | `parsers/molecule/coref_alt.py` had 139 lines changed; only one new test added. Cross-page join edge cases under-tested. | `src/mbforge/parsers/molecule/coref_alt.py` | **OPEN** |
| D-4 | Python | `backends/zvec_backend.py:_validate_index_payload` raises `ValidationError` but `zvec_backend.py:163` line wrap produces 3-line error message — reformat for grep-friendliness. | `src/mbforge/backends/zvec_backend.py:163` | **RESOLVED 2026-07-07** (`backends/zvec_backend.py` deleted; replaced by `openkb` + `pageindex` in `4fbde55`) |
| D-5 | Python | `utils/helpers.py:run_sync` signature uses `"Callable[..., Any]"` quoted form in some places, unquoted in others. Pick one (Python 3.11+ allows unquoted). | `src/mbforge/utils/helpers.py` | **OPEN** |
| D-6 | Frontend | `_utils.ts` header comment says "HTTP communication layer — replaces Tauri IPC for web mode" but file is still in `api/tauri/` directory. Move to `api/http/`. | `frontend/src/api/tauri/_utils.ts` | **RESOLVED 2026-07-07** (file moved to `api/http/_utils.ts`; `api/tauri/` directory removed) |
| D-7 | Deps | `pyproject.toml:79` `pandas>=3.0.3` — verify against current resolved version in `uv.lock`. | `pyproject.toml` | **OPEN** |
| D-8 | Deps | `langchain>=0.3.0`, `langgraph>=0.4.0` floors are loose; need `uv lock` snapshot of resolved versions to spot breaking changes. | `pyproject.toml`, `uv.lock` | **OPEN** |
| X-1 | Docs | `AGENTS.md` "Storage locations" references `{root}/.mbforge/knowledge_base.db` but `.gitignore` typo (C-2) says `.mbccforge/`. Reconcile. | `AGENTS.md`, `.gitignore` | **RESOLVED 2026-07-07** (C-2 fixed; AGENTS.md path is correct) |
| X-2 | Docs | `README.md` "Tech Stack" still mentions Tauri v2 / Rust in some lines — verify after rewrite. | `README.md` | **OPEN** |
| X-3 | Docs | `docs/REFERENCES.md` lists PyMuPDF, lopdf, ChromaDB, rusqlite — all removed. Updated 2026-06-29. | `docs/REFERENCES.md` | **RESOLVED** |

## P3 — Low (Future Features & Style Polish)

**Phase 0 明确不做（推迟到 Phase 1-3）**:

| ID | Area | Feature | Rationale |
|---|---|---|---|
| F-1 | Architecture | Evidence Links（点击分子跳转 PDF bbox 高亮）| 低频场景，不是开源科研工具的核心价值。Phase 0 只做 Figure-Molecule Linking（查看 crop）。 |
| F-2 | Agent | Drug-Design Workflows（SAR 对比、multi-target 分析、反向合成建议）| 需要高准确率数据（95%+）+ 领域知识图谱，Phase 0 模型能力不支持。 |
| F-3 | Database | 跨文献分子去重聚合（同一 SMILES 在多篇文献 → 单条记录 + 多条 evidence）| 需要全局索引 + 中心化服务，Phase 0 是 per-project vault。 |
| F-4 | Platform | 数据网络效应（用户校正 → 模型改进飞轮）| 需要中心化服务 + 隐私方案，Phase 0 是本地单用户工具。 |
| F-5 | Model | SMILES 识别准确率 95%+（fine-tune MolScribe）| 需要 1000+ 篇标注文献 + GPU 集群，单独立项。Phase 0 接受 85-90% baseline。 |

**已有（样式和类型标注优化）**:

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| S-1 | Python | `server.py` legacy `_CORE_BACKENDS` prewarm comment lists 5 backends; all are comment-only since the migration. Update to no-op prewarm or remove dead reference. (Zvec itself removed in `4fbde55`; only `molscribe` + `moldet` are still real sidecar backends.) | `src/mbforge/server.py:54` | **RESOLVED 2026-07-07** (`_CORE_BACKENDS` no longer referenced; prewarm loop verified as no-op) |
| S-2 | Python | `__main__.py` comment is English; `server.py` docstrings are mixed Chinese/English. Pick one convention. | `src/mbforge/__main__.py`, `src/mbforge/server.py` | **OPEN** |
| S-3 | Frontend | `frontend/src/api/sse.ts` uses `EventSource` API; verify behaviour across browsers (Chromium OK, Safari has quirks). | `frontend/src/api/sse.ts` | **OPEN** |
| S-4 | Repo | `assets/models/` referenced in `AGENTS.md` but directory may not exist or be gitignored. | `assets/models/` | **OPEN** |

---

## How this board stays current

- New audits land here as dated P0–P3 sections; resolved items move to a "RESOLVED <date>" tag with the date.
- The deprecated root `TODO.md` is removed; do not recreate it.
- All `code-review` runs and comment-audit sweeps MUST append to this file, not a side file.
- Each P0 item should have a corresponding `git blame` entry or PR link when resolved.

## Recent Resolutions (2026-06-29 migration)

| ID | Description |
|---|---|
| X-3 | `docs/REFERENCES.md` updated: removed lopdf/PyMuPDF/ChromaDB/rusqlite, added pdfplumber/pypdfium2/Zvec/LangGraph. (Subsequently: Zvec itself removed in `4fbde55` and replaced by OpenKB + PageIndex — second pass applied 2026-07-05.) |
| X-2 | `README.md` rewritten: removed all Tauri v2 / Rust mentions, added FastAPI + LangGraph stack table. (Subsequently: Zvec mentions replaced by OpenKB, 5-stage → 6-stage pipeline, src-tauri/ removed entirely — second pass 2026-07-05.) |
| X-4 | `src-tauri/` directory deleted from working tree (~29 GB) — Rust workspace history preserved via `git log -- src-tauri/`. |
| — | `CLAUDE.md` created at repo root (previously session-only at `~/.claude/CLAUDE.md`). |
| — | `AGENTS.md` rewritten to reflect Python-only backend (subsequently: OpenKB + 18 routers + 6-stage pipeline corrected 2026-07-05). |
| R-9 | `CLAUDE.md` no longer references `archived/agent/` — error examples rewritten during 2026-07-05 refresh. |