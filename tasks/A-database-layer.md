# Task A: 数据库抽象层重构

> 难度: ★★★★☆ (Hard)
> 优先级: P0 — 基础设施，阻塞 Task B
> 预计工作量: 3-4 天
> 依赖: 无（可立即开始）
> 被依赖: Task B（分子三层迁移依赖本任务的 schema 定义）

---

## 目标

从第一性原理出发，建立类型安全、可迁移、低样板的数据库抽象层。消除手写 SQL DDL 散落、row.get(0) 按索引映射、迁移管理为零的问题。

---

## 当前问题

| 问题 | 影响 | 涉及文件 |
|------|------|---------|
| 手写 SQL DDL 散落在 6+ 文件 | 改 schema 需连锁修改 | molecule_store.rs, molecule_db.rs, file_cache.rs, content_cache.rs |
| row.get(0) 按索引映射 | 改列顺序必漏 | 所有 `.query_map()` 调用点 |
| 迁移管理零 | fingerprint 列用 `.ok()` hack | molecule_store.rs:380 |
| FTS5 与主表手动同步 | insert/update/delete 各写一遍 | molecule_store.rs:396-437 |
| 重复样板代码 | open → init_schema → CRUD → row_to_x | 每个存储模块 |

---

## 设计规范

### 第一层: Schema 定义（声明式）

用 Rust struct 定义表结构，通过 derive macro 自动生成 DDL、行映射、参数绑定。

```rust
// 目标 API（规范，非最终实现）
#[derive(Table)]
#[table(name = "molecules")]
pub struct MoleculeRow {
    #[column(primary_key)]
    pub mol_id: String,

    #[column(not_null)]
    pub smiles: String,           // Layer 1: 事实来源

    #[column(nullable)]
    pub esmiles: Option<String>,  // Layer 2: 可选插件

    #[column(nullable, json)]
    pub tags: Option<serde_json::Value>,

    #[column(index)]
    pub source_doc: String,

    #[column(nullable)]
    pub fingerprint: Option<Vec<u8>>,

    // ... 其他字段
}
```

**规范要求**:
- `Table` trait 定义: `table_name()`, `columns()`, `ddl_sql()`, `index_sqls()`, `from_row()`, `to_params()`
- `#[column]` 属性支持: `primary_key`, `not_null`, `nullable`, `index`, `unique`, `default`, `json`, `auto`
- FTS5 虚拟表通过 `#[derive(Fts5Table)]` 定义，自动生成 `sync_insert_sql()`, `sync_update_sql()`, `sync_delete_sql()`
- 枚举类型实现 `DbType` trait，自动生成 CHECK 约束

### 第二层: 数据库连接（Schema 管理）

```rust
// 目标 API
pub struct DbConnection {
    conn: rusqlite::Connection,
}

impl DbConnection {
    pub fn open(path: &Path) -> Result<Self, String>;
    pub fn register<T: Table>(&mut self) -> Result<(), String>;
    pub fn register_fts5<T: Fts5Table>(&mut self) -> Result<(), String>;
    pub fn query<T: Table>(&self) -> QueryBuilder<T>;
    pub fn execute(&self, sql: &str, params: &[&dyn ToSql]) -> Result<usize, String>;
}
```

**规范要求**:
- `open()` 自动设置 `PRAGMA journal_mode=WAL` 和 `PRAGMA foreign_keys=ON`
- `register()` 执行 `CREATE TABLE IF NOT EXISTS` + 索引 + pending 迁移
- 所有表通过 `register()` 统一初始化，不各自调用 `init_schema()`

### 第三层: 类型安全查询（Builder 模式）

```rust
// 目标 API
db.query::<MoleculeRow>()
    .select()
    .where_(MoleculeRow::source_doc, Eq, doc_id)
    .order_by(MoleculeRow::created_at, Desc)
    .limit(50)
    .fetch()  // -> Result<Vec<MoleculeRow>, String>
```

**规范要求**:
- `where_()` 的字段参数通过 `Field<T>` trait 保证编译时类型安全
- `Op` 枚举: `Eq`, `Ne`, `Gt`, `Lt`, `Like`, `In`, `IsNull`, `IsNotNull`
- `fetch()` 返回 `Vec<T>`，`fetch_one()` 返回 `Option<T>`
- 支持 `insert(&record)`, `update(&record).where_(...)`, `delete().where_(...)`

### 迁移系统

```rust
#[derive(Table)]
#[table(name = "molecules")]
#[migration(version = 1, name = "add_fingerprint",
    up = "ALTER TABLE molecules ADD COLUMN fingerprint BLOB")]
#[migration(version = 2, name = "esmiles_to_smiles",
    up = "ALTER TABLE molecules ADD COLUMN smiles TEXT; \
          UPDATE molecules SET smiles = esmiles WHERE smiles IS NULL;")]
pub struct MoleculeRow { ... }
```

**规范要求**:
- 自动维护 `_migrations` 表（table_name, version, applied_at）
- 启动时检查当前 version < 注册的最高 version → 顺序执行缺失的 up
- 迁移必须幂等（使用 IF NOT EXISTS 等）
- 保留现有 `IF NOT EXISTS` 幂等策略，在其上叠加版本控制

---

## 实施步骤

### Phase 1: trait 定义 + 基础设施
- [ ] `core/db/mod.rs` — 模块声明
- [ ] `core/db/table.rs` — `Table` trait, `Fts5Table` trait, `DbType` trait
- [ ] `core/db/column.rs` — `Column` 定义, `ColumnAttr` 枚举
- [ ] `core/db/connection.rs` — `DbConnection` 封装

### Phase 2: derive macro
- [ ] `core/db/macros/` — proc macro crate（`#[derive(Table)]`, `#[derive(Fts5Table)]`）
- [ ] 或：手动实现 `Table` trait（如果 proc macro 太复杂，先用手写 impl 验证设计）

### Phase 3: 迁移框架
- [ ] `core/db/migration.rs` — `Migration` struct, `MigrationSet`, `_migrations` 表
- [ ] 集成到 `DbConnection::register()`

### Phase 4: 查询构造器
- [ ] `core/db/query.rs` — `QueryBuilder`, `Select`, `Delete`, `Op`, `Order`
- [ ] 类型安全字段引用

### Phase 5: 验证
- [ ] 用 `FileCache` 做第一个迁移示范（最简单）
- [ ] 确认 `cargo check` + `cargo test` 通过

---

## 文件范围

| 文件 | 操作 |
|------|------|
| `src-tauri/src/core/db/mod.rs` | 新建 |
| `src-tauri/src/core/db/table.rs` | 新建 |
| `src-tauri/src/core/db/column.rs` | 新建 |
| `src-tauri/src/core/db/connection.rs` | 新建 |
| `src-tauri/src/core/db/migration.rs` | 新建 |
| `src-tauri/src/core/db/query.rs` | 新建 |
| `src-tauri/src/core/mod.rs` | 修改（添加 `pub mod db;`） |
| `src-tauri/Cargo.toml` | 可能添加 proc-macro 依赖 |

---

## 上下文索引

| 参考 | 位置 | 说明 |
|------|------|------|
| 当前 molecule_store schema | `src-tauri/src/core/molecule/molecule_store.rs:325-369` | 现有 CREATE TABLE |
| 当前 molecule_db schema | `src-tauri/src/core/molecule/molecule_db.rs:92-107` | 现有关系表 |
| 当前 file_cache schema | `src-tauri/src/core/document/file_cache.rs:33-45` | 现有缓存表 |
| 当前 content_cache schema | `src-tauri/src/core/document/content_cache.rs:42-55` | 现有缓存表 |
| rusqlite API | https://docs.rs/rusqlite | 底层依赖 |
| ARCHITECTURE.md §六 | `ARCHITECTURE.md` | 存储架构设计 |
| STANDARDS.md | `tasks/STANDARDS.md` | 开发规范 |
