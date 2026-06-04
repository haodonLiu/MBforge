//! 数据库抽象层 — 类型安全、可迁移、低样板
//!
//! 三层 API:
//! - Layer 1: `Table` trait + `ColumnDef` — 声明式 schema 定义
//! - Layer 2: `DbConnection` — 统一连接管理 + 表注册 + 迁移
//! - Layer 3: `QueryBuilder` — 类型安全查询（SELECT / INSERT / DELETE）
//!
//! 不引入 Diesel/SeaORM，底层仍是 rusqlite。

pub mod connection;
pub mod migration;
pub mod query;
pub mod table;

pub use connection::DbConnection;
pub use migration::{Migration, MigrationSet};
pub use query::{DeleteQuery, QueryBuilder, SelectQuery};
pub use table::{ColumnDef, FieldRef, Fts5Table, Op, Order, Table};
