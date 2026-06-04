# Agent Systems with Harness Engineering — Reference Notes

**Paper**: "Agent Systems with Harness Engineering"
**Authors**: Xinyu Tang et al.
**Published**: May 2026
**License**: CC BY 4.0
**Local copy**: N/A (reference notes only)

---

## 1. Core Thesis

> "Even highly capable LLMs produce systematic failures in long-horizon settings without adequate system support." — 论文摘要

> "These stem from a structural mismatch between the single-turn generative interface of LLMs and the stateful, iterative nature of real-world problem solving." — 论文核心诊断

The paper formalizes **harness engineering** as "the joint optimization of both the harness and the model it supports." The harness is defined as "the surrounding infrastructure."

### 协同关系（论文原文）

> "Structured memory, error recovery, and adaptive context management unlock model potential, while strong models enable sophisticated workflows."

This relationship is "inherently synergistic" — 好的 harness 释放模型潜力，强的模型使更复杂的工作流成为可能。

A well-designed harness unlocks latent model potential through three mechanisms:

- **Memory** — maintaining state and knowledge across turns
- **Error recovery** — detecting, diagnosing, and correcting failures
- **Adaptive context** — dynamically adjusting what the model sees based on task phase and complexity

### 五个研究贡献

1. **结构化分类法** — "agent workflows, memory systems, skill libraries, and multi-agent orchestration"
2. **性能贡献分析** — "how each component contributes to system-level performance"
3. **设计原则** — "distilled design principles and architectural trade-offs"
4. **优化策略** — "optimization strategies from both the scaffold and model sides"
5. **评估基准** — "evaluation benchmarks across software engineering, deep research, tool use, computer use, and scientific discovery"

### 定位

论文旨在成为 "a practical reference for building reliable, scalable, and controllable agent systems through principled harness engineering."

---

## 2. Harness Components Taxonomy

The paper identifies four primary categories of harness components:

### 2.1 Agent Workflows

Task decomposition, planning, and execution orchestration. This includes:

- Decomposing complex goals into sub-tasks
- Selecting execution order and dependencies
- Monitoring progress and triggering replanning when needed

### 2.2 Memory Systems

Four distinct memory types, each serving a different function:

| Type        | Function                                      | Persistence |
|-------------|-----------------------------------------------|-------------|
| Short-term  | Current task context, recent actions           | Session     |
| Long-term   | Accumulated knowledge, user preferences        | Cross-session |
| Episodic    | Structured records of past interactions        | Cross-session |
| Semantic    | Abstracted knowledge distilled from episodes   | Cross-session |

### 2.3 Skill Libraries

Reusable action patterns and tool compositions. Skills are:

- Parameterized templates for common operations
- Composable — simpler skills combine into complex ones
- Discoverable — agents can search and select relevant skills

### 2.4 Multi-Agent Orchestration

Coordination across specialized agents:

- Role assignment based on task requirements
- Communication protocols between agents
- Shared vs. private state management
- Conflict resolution when agents disagree

---

## 3. Key Design Principles

### 3.1 Joint Optimizability

The harness and model are jointly optimizable — neither dominates. A stronger
model with a weak harness underperforms a weaker model with a strong harness
in many long-horizon tasks. Optimization must consider both simultaneously.

### 3.2 Structural Mismatch

There is a fundamental mismatch between the single-turn LLM interface
(prompt in, response out) and the stateful, iterative nature of real
problem solving. The harness bridges this gap by maintaining state,
tracking progress, and managing the interaction loop.

### 3.3 Memory as the Bridge Between Turns

Without memory, agents are stateless. Each turn starts from scratch.
Memory is what transforms a sequence of independent LLM calls into a
coherent agent that builds on its own history. The quality and structure
of memory directly determines agent capability ceiling.

### 3.4 Skill Libraries Reduce Cognitive Load

Agents do not need to reinvent patterns. When an agent has access to a
library of proven tool-use patterns, it can focus its limited context
window on the novel aspects of the current task rather than re-deriving
standard procedures.

---

## 4. Relevance to MBForge

### 4.1 Agent Workflows — Partially Addressed

Our ReAct loop (`src-tauri/src/core/agent.rs`) implements a workflow:
LLM call -> tool execution -> result injection -> repeat. However, it is
limited to a single agent with no explicit task decomposition or planning
phase. The agent reasons and acts in a flat loop.

**Gap**: No hierarchical task decomposition. Complex multi-step chemistry
tasks (e.g., "find all papers about SAR for compound X, extract molecules,
validate structures, compute similarities") rely entirely on the LLM's
ability to plan within a single ReAct chain.

### 4.2 Memory Systems — Good Coverage, Missing Episodic

`MemoryManager` in `src-tauri/src/core/memory/` implements 6 memory
categories. This maps well to the paper's short-term and long-term types.

**Gap**: No episodic memory. Past interactions are not stored as structured
episodes that can be retrieved by similarity. The agent cannot say "last
time I analyzed a similar PDF, the key findings were..." Semantic memory
(distilled knowledge from episodes) is also absent.

### 4.3 Skill Libraries — Exists but Underutilized

`SkillsManager` exists in the codebase but is underutilized. The agent
has access to 25+ tools registered in `core/executor/`, but these are
raw tool definitions, not composed skill patterns.

**Gap**: No abstraction layer above individual tools. A "skill" would be
something like "extract-and-validate-molecules-from-pdf" — a sequence of
tool calls with known-good parameters and error handling. Currently the
agent must derive such sequences from scratch each time.

### 4.4 Multi-Agent — Not Implemented

There is no multi-agent orchestration. The system runs a single ReAct
agent that handles all domains equally.

**Gap**: Domain-specific agents could significantly improve quality:
- **Molecule expert** — deep knowledge of SMILES, InChI, structure
  validation, Tanimoto similarity, substructure search
- **Document analyst** — specialized in PDF parsing, section extraction,
  figure-caption association
- **SAR specialist** — structure-activity relationship reasoning,
  scaffold analysis, pharmacophore identification

---

## 5. Concrete Implications for MBForge

### 5.1 Episodic Memory

Store past interactions as structured episodes containing:
- The original task/prompt
- Tools used and their arguments
- Outcomes (success/failure, key results)
- Context (project, document type, molecule class)

Enable retrieval by: embedding similarity, keyword match, or metadata
filter (e.g., "show me past PDF extractions for kinase inhibitors").

**Implementation sketch**: Add an `episodes` table to the SQLite store
in `molecule_store.rs`, with FTS5 on task description and results.
Expose a `recall_episodes` tool to the agent.

### 5.2 Skill Extraction

After successful task completion, auto-extract the tool-use trajectory
into a reusable skill template:
- Identify the tool call sequence
- Parameterize variable parts (file paths, molecule SMILES, etc.)
- Store with success conditions and common failure modes

**Implementation sketch**: Add a post-task hook in `agent.rs` that,
on successful completion, serializes the trajectory into a skill
template stored in `skills/` directory.

### 5.3 Multi-Agent for Chemistry Tasks

Implement domain-specific agent roles that can be invoked as sub-agents:
- Register specialized tool subsets per role
- Use the existing Agent architecture with role-specific system prompts
- Orchestrate via a meta-agent that delegates based on task domain

**Implementation sketch**: Extend `Agent::new()` to accept a role
configuration that filters available tools and injects domain-specific
system prompt fragments.

### 5.4 Adaptive Context

Dynamically adjust the context window based on task complexity:
- Simple queries: minimal context, fast response
- Complex analysis: expand context with relevant memory, skills, and
  document excerpts
- Use task classification (already exists in `classify_pdf`) to
  determine context budget

**Implementation sketch**: Add a context budget manager that allocates
tokens across: system prompt, memory recall, skill templates, document
context, and conversation history — prioritizing based on task phase.

---

## 6. Takeaway

The paper's central argument — that harness engineering is as important as
model capability — maps directly to MBForge's architecture. We have a
capable Rust agent with good tooling, but the harness (memory, skills,
multi-agent) has gaps that limit the system's effective capability.
Investing in these harness components will yield disproportionate returns
compared to further model upgrades alone.
