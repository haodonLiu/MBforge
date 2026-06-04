# Task B: 分子三层表示迁移

> 难度: ★★★☆☆ (Medium)
> 优先级: P0 — 核心数据模型重构
> 预计工作量: 2-3 天
> 依赖: Task A（需要新的 Table trait + 迁移系统）
> 被依赖: 无

---

## 目标

将分子存储从"E-SMILES 作为主格式"迁移到"SMILES 为事实来源 + E-SMILES 为可选插件"的三层架构。

---

## 三层表示规范

```
Layer 3: MoleCode ─── LLM 推理（运行时临时，不持久化）
    ↕ 双向转换（Python sidecar /molecode/convert）
Layer 2: E-SMILES ─── 语义插件（nullable，tags JSON 元数据）
    ↕ 解析分离（去掉标签 → 纯 SMILES）
Layer 1: SMILES ───── 事实来源（NOT NULL，RDKit/Chematic 直接可用）
```

**核心规则**:
- 所有化学计算（Chematic、RDKit）使用 `smiles` 字段，永不接触 `esmiles`
- `esmiles` 仅在需要语义标签时写入，读取时可选
- `tags` JSON 存储解析后的标签元数据（`{"R1":"Me","source":"claim_parser"}`）
- MoleCode 不持久化，Agent 推理时调用 Python sidecar 临时生成

---

## 当前 → 目标 schema 变更

```sql
-- 当前
CREATE TABLE molecules (
    mol_id TEXT PRIMARY KEY,
    esmiles TEXT NOT NULL,    -- 标签污染，RDKit 需清洗
    name TEXT,
    ...
);

-- 目标（Task A 的 Table trait 定义）
CREATE TABLE molecules (
    mol_id TEXT PRIMARY KEY,
    smiles TEXT NOT NULL,      -- Layer 1: 纯净 SMILES
    esmiles TEXT,              -- Layer 2: 可选，nullable
    tags TEXT,                 -- JSON: 语义标签元数据
    name TEXT,
    source_doc TEXT,
    activity REAL,
    activity_type TEXT,
    units TEXT DEFAULT 'nM',
    source_type TEXT DEFAULT 'text',
    status TEXT DEFAULT 'confirmed',
    properties TEXT,
    tags_list TEXT,            -- 原 tags Vec<String>，改名避免与新 tags 列冲突
    notes TEXT,
    fingerprint BLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- FTS5 重建：索引纯净 SMILES
CREATE VIRTUAL TABLE mol_search USING fts5(
    name, notes, smiles,      -- ← smiles 替代 esmiles
    content='molecules', content_rowid='rowid'
);
```

---

## 实施步骤

### Step 1: 数据迁移脚本
- [ ] 写迁移 SQL：`ALTER TABLE molecules ADD COLUMN smiles TEXT`
- [ ] 迁移逻辑：`UPDATE molecules SET smiles = strip_esmiles_tags(esmiles) WHERE smiles IS NULL`
- [ ] 添加 `NOT NULL` 约束（迁移完成后）
- [ ] 添加 `idx_mol_smiles` 索引

### Step 2: molecule_store.rs 重写
- [ ] 使用 Task A 的 `Table` trait 定义 `MoleculeRow`
- [ ] 所有查询从 `esmiles` 改为 `smiles`
- [ ] `add_molecule()` 接受 `(smiles, esmiles, tags)` 三元组
- [ ] `search_by_esmiles()` 重命名为 `search_by_smiles()`

### Step 3: FTS5 重建
- [ ] `DROP TABLE mol_search`（旧的 esmiles 索引）
- [ ] `CREATE VIRTUAL TABLE mol_search USING fts5(name, notes, smiles)`
- [ ] 重建索引数据

### Step 4: 调用点更新
- [ ] `chem_validate.rs`：去掉 `sanitize_esmiles()`，直接用 `smiles`
- [ ] `core/chem.rs`：所有函数接受纯 SMILES
- [ ] `extract_esmiles_candidates()` → 提取后分离为 `(smiles, esmiles, tags)`
- [ ] `association.rs`：更新分子关联逻辑
- [ ] Agent 工具：`search_by_smiles` 替代 `search_by_esmiles`

### Step 5: 前端适配
- [ ] 分子详情页：显示 `smiles`（主）+ `esmiles`（可选标签）
- [ ] 搜索接口：使用 `smiles` 字段

---

## 文件范围

| 文件 | 操作 |
|------|------|
| `src-tauri/src/core/molecule/molecule_store.rs` | 重写 |
| `src-tauri/src/core/molecule/molecule_db.rs` | 适配 |
| `src-tauri/src/core/molecule/molecule_engine.rs` | 适配 |
| `src-tauri/src/core/molecule/molecule_dedup.rs` | 适配 |
| `src-tauri/src/parsers/chem_validate.rs` | 重写（去掉 sanitize） |
| `src-tauri/src/parsers/association.rs` | 适配 |
| `src-tauri/src/commands/molecule.rs` | 适配 |
| `src-tauri/src/core/executor/molecule.rs` | 适配 |

---

## 上下文索引

| 参考 | 位置 | 说明 |
|------|------|------|
| 当前 molecule schema | `src-tauri/src/core/molecule/molecule_store.rs:325-369` | 现有 CREATE TABLE |
| E-SMILES 标签格式 | `src-tauri/docs/esmiles/` | E-SMILES 规范 |
| sanitize_esmiles | `src-tauri/src/parsers/chem_validate.rs` | 当前清洗逻辑 |
| extract_esmiles_candidates | `src-tauri/src/parsers/molecule_extractor.rs` | 正则提取 |
| ARCHITECTURE.md §四 | `ARCHITECTURE.md` | 三层表示架构 |
| STANDARDS.md | `tasks/STANDARDS.md` | 开发规范 |
