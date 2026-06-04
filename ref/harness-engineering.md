# Agent Harness Engineering: A Survey — Reference Notes

> Paper reference and MBForge architecture mapping via the ETCLOVG taxonomy.

## 1. Paper Info

| Field | Value |
|-------|-------|
| Title | Agent Harness Engineering: A Survey |
| Authors | Junjie Li et al. |
| Year | 2026 |
| Scope | Survey of 170+ open-source agent projects |
| Contribution | Proposes ETCLOVG seven-layer taxonomy for classifying agent infrastructure |

## 2. Core Thesis

LLM agent reliability in production depends more on the **infrastructure (harness)** wrapping the model than on the model itself. The base model provides capability; the harness determines whether that capability translates into dependable real-world behavior.

Three-phase evolution of agent engineering practice:

1. **Prompt engineering** — crafting better instructions for the LLM (2022-2023)
2. **Context engineering** — managing what information reaches the model window (2023-2024)
3. **Harness engineering** — building the full infrastructure stack around the agent (2024-present)

The harness is the difference between a demo and a product. A weak harness makes even the strongest model unreliable; a strong harness makes a modest model useful.

## 3. ETCLOVG Seven-Layer Taxonomy

The paper identifies seven layers of agent infrastructure. Each layer addresses a distinct class of production concerns.

### E — Execution Environment

Runtime, sandboxing, resource management. Where and how the agent process runs.

- Process isolation and lifecycle management
- Resource limits (CPU, memory, disk, network)
- Sandboxed file system / network access
- Dependency management and sidecar orchestration

### T — Tool Interface

API design, tool registration, error handling. How the agent discovers and invokes external capabilities.

- Tool schema definition (name, description, parameters)
- Registration and discovery mechanisms
- Uniform error handling and timeout policies
- Native vs. sidecar execution routing

### C — Context Management

Memory, retrieval, window management. What the agent "knows" at each step.

- Short-term context (conversation window, truncation strategy)
- Long-term memory (persistent categories, retrieval)
- Knowledge base integration (vector search, structured queries)
- Context window budgeting and prioritization

### L — Lifecycle / Orchestration

Task decomposition, planning, multi-agent coordination. How complex tasks are broken down and executed.

- ReAct / plan-then-execute loops
- Iteration limits and termination conditions
- Multi-agent delegation and coordination
- Trajectory tracking and step history

### O — Observability

Logging, tracing, debugging, monitoring. How humans understand what the agent did and why.

- Structured logging of agent decisions
- Tool call tracing with inputs/outputs
- Performance metrics (latency, token usage, cost)
- Debug replay and post-hoc analysis

### V — Verification

Output validation, safety checks, testing. How the system confirms agent outputs are correct and safe.

- Domain-specific validation (e.g., chemical structure checks)
- Output format verification
- Grounded-ness / hallucination detection
- Automated test harnesses for agent behavior

### G — Governance

Permissions, audit trails, cost control. Who controls what the agent can do and how much it can spend.

- Permission models (read-only vs. read-write)
- Cost tracking and budget enforcement
- Audit trails for compliance
- Rate limiting and escalation policies

## 4. Key Insights

### The harness is the primary reliability driver

The paper's central finding: across 170+ projects, harness quality correlates more strongly with production reliability than base model quality. A well-harnessed GPT-4-class model outperforms a poorly-harnessed frontier model in real deployments.

### Ecosystem coverage gaps

The survey maps existing open-source projects to ETCLOVG layers and finds significant gaps. Most projects concentrate on T (Tool Interface) and C (Context), while O (Observability) and G (Governance) are consistently underdeveloped. This mirrors the maturity curve — teams build what they need first and defer governance.

### Cost-quality-speed trilemma

Every agent system faces a three-way tension:

- **Quality**: more LLM calls, larger context, validation passes → better output
- **Speed**: fewer calls, smaller context, skip validation → faster response
- **Cost**: quality and speed both consume tokens and compute

There is no configuration that maximizes all three. Harness engineering is largely about navigating this tradeoff explicitly rather than implicitly.

### Capability-control tradeoff

More capable agents (more tools, longer trajectories, autonomous planning) require proportionally more governance infrastructure. An agent that can write files needs permission controls; an agent that can call external APIs needs cost tracking. Capability without governance is a liability.

## 5. Relevance to MBForge

Mapping MBForge's current architecture to the ETCLOVG taxonomy.

### E — Execution: Strong

MBForge uses a **Tauri sidecar model** where the FastAPI model server (`uvicorn` on port 18792) is spawned as a child process by the Tauri shell. Key infrastructure:

- `src-tauri/src/main.rs` — sidecar lifecycle management (spawn, health check, shutdown)
- Process isolation between Rust host and Python model server
- Tauri v2 provides OS-level sandboxing for the desktop application
- Resource management via Tauri's process supervision

### T — Tool Interface: Strong

25+ Agent tools registered through a structured `ToolRegistry` pattern:

- `src-tauri/src/core/executor/mod.rs` — orchestrator wiring all tool submodules
- `src-tauri/src/core/executor/fs.rs` — file system tools (search, read, list)
- `src-tauri/src/core/executor/kb.rs` — knowledge base tools (search, structure, pages)
- `src-tauri/src/core/executor/document.rs` — document tools (abstracts, overviews, listing)
- `src-tauri/src/core/executor/molecule.rs` — molecule analysis and Markush overlap
- `src-tauri/src/core/executor/literature.rs` — arXiv/PMC paper access
- Uniform `ToolInfo` schema: name, description, JSON Schema parameters
- Native vs. sidecar routing: native tools execute in Rust, others proxy to Python

### C — Context: Strong

Multi-layered context and memory system:

- `src-tauri/src/core/memory/memory.rs` — `MemoryManager` with 6 persistent categories: `profile`, `preferences`, `entities`, `events`, `cases`, `patterns`
- `src-tauri/src/core/context.rs` — `LayeredContext` for conversation window management
- `src-tauri/src/core/document/knowledge_base.rs` — vector knowledge base integration
- `SemanticCache` for embedding-based retrieval
- LanceDB-based knowledge base for structured and vector queries
- `AGENT_MAX_HISTORY_ROUNDS` and `AGENT_MAX_TOTAL_TOKENS` constants for window budgeting

### L — Lifecycle: Moderate

Single-agent ReAct loop with trajectory tracking:

- `src-tauri/src/core/agent.rs` — `Agent` struct with `chat()` / `chat_stream()` methods implementing the ReAct loop
- `AGENT_MAX_ITERATIONS` caps the tool-call loop
- `src-tauri/src/core/memory/trajectory.rs` — `TrajectoryTracker` records up to 500 steps per session with `step_type`, `uri`, `query`, `result_count`, `duration_ms`, `timestamp`
- `src-tauri/src/core/memory/skills.rs` — `SkillsManager` for learned skill extraction
- **Gap**: single-agent only, no multi-agent orchestration or task decomposition

### O — Observability: Weak

Minimal structured observability:

- `DocProgressEvent` in `src-tauri/src/parsers/pipeline.rs` and `pipeline/merge.rs` — emits progress events during PDF parsing
- `processing_log` — per-document processing log
- `TrajectoryTracker` records tool call history (step type, URI, duration) but as flat JSON, not structured traces
- **No** agent decision audit trail (why the agent chose a tool, what alternatives were considered)
- **No** token/cost accounting per session or per tool call
- **No** distributed tracing or correlation IDs across Rust-Python boundary

### V — Verification: Partial

Domain-specific validation exists, general verification does not:

- `src-tauri/src/parsers/chem_validate.rs` — RDKit-backed chemical structure validation (SMILES parseability, canonicalization, Kekulization, aromaticity, atom count)
- `src-tauri/src/parsers/post_process.rs` — LLM output JSON repair and structural parsing
- **No** general output verification framework (format checking, grounded-ness tests)
- **No** automated agent behavior tests or regression harness
- **No** hallucination detection for non-chemical outputs

### G — Governance: Minimal

Basic path safety, no systematic governance:

- `assert_within_root` in `src-tauri/src/core/helpers.rs`, `src-tauri/src/commands/file_ops.rs`, `src-tauri/src/core/executor/fs.rs` — prevents file operations outside project root
- **No** cost tracking or budget enforcement
- **No** permission model (agent has full access to all registered tools)
- **No** audit trail for compliance
- **No** rate limiting on LLM calls or tool invocations

## 6. Gaps in MBForge (ETCLOVG Analysis)

Summary of gaps ranked by production risk.

### Observability — No structured tracing, no agent decision audit trail

**Current state**: TrajectoryTracker records tool calls as flat JSON. DocProgressEvent covers PDF parsing only.

**What's missing**:
- Structured trace format (OpenTelemetry-compatible spans)
- Agent reasoning trace: why each tool was selected, what alternatives were rejected
- Token accounting per tool call and per session
- Cross-boundary correlation IDs (Rust invoke → Python sidecar → back)
- Dashboard or replay capability for debugging agent sessions

**Impact**: When an agent gives a wrong answer, there is no way to reconstruct the decision path. Debugging requires manual reproduction.

### Verification — No general output verification

**Current state**: chem_validate.rs handles SMILES validation. post_process.rs repairs malformed JSON.

**What's missing**:
- Output format validation for all tool types (not just chemistry)
- Grounded-ness checks: does the agent's answer actually cite retrieved sources?
- Regression test harness: replay past sessions and verify output stability
- Confidence scoring on agent responses

**Impact**: Agent can produce plausible but ungrounded answers with no automated way to catch them.

### Governance — No cost tracking, no permission model

**Current state**: assert_within_root prevents path traversal. Nothing else.

**What's missing**:
- Per-session and per-tool cost tracking (tokens, API calls, wall time)
- Budget enforcement (stop agent when cost exceeds threshold)
- Permission model: differentiate read-only tools from write/delete tools
- Audit log: who triggered what agent action, when, at what cost
- Rate limiting on LLM and sidecar calls

**Impact**: No guardrails against runaway agent behavior. A misconfigured or adversarial prompt could consume unbounded resources.

### Lifecycle — Single-agent only, no multi-agent orchestration

**Current state**: One Agent struct, one ReAct loop, one tool registry.

**What's missing**:
- Multi-agent delegation (specialist agents for chemistry, literature, file operations)
- Task decomposition: breaking complex queries into sub-tasks
- Agent-to-agent communication protocol
- Parallel tool execution where independent

**Impact**: Complex queries that span multiple domains (e.g., "find papers about this molecule class, then analyze their SAR, then suggest modifications") must be handled sequentially by a single agent, limiting throughput and specialization.

## 7. Prioritized Improvement Roadmap

Based on the ETCLOVG gap analysis, ordered by production impact:

| Priority | Layer | Improvement | Effort |
|----------|-------|-------------|--------|
| P0 | O | Structured tracing for agent decisions | Medium |
| P0 | G | Token/cost accounting per session | Low |
| P1 | V | Output grounded-ness checks | Medium |
| P1 | G | Budget enforcement with auto-stop | Low |
| P1 | O | Cross-boundary correlation IDs | Medium |
| P2 | G | Permission model for tool categories | Medium |
| P2 | L | Multi-agent orchestration | High |
| P2 | V | Regression test harness for agent behavior | High |
| P3 | O | Agent session replay capability | High |
| P3 | G | Full audit trail with compliance export | Medium |
