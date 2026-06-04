//! 数据库抽象层 — 类型安全、低样板
//!
//! 三层 API:
//! - Layer 1: `Table` trait + `ColumnDef` — 声明式 schema 定义
//! - Layer 2: `DbConnection` — 统一连接管理 + 表注册
//! - Layer 3: `QueryBuilder` — 类型安全查询（SELECT / INSERT / DELETE）
//!
//! 不引入 Diesel/SeaORM，底层仍是 rusqlite。
//! Schema 管理采用幂等策略：CREATE TABLE IF NOT EXISTS + ALTER TABLE .ok()

pub mod connection;
pub mod query;
pub mod table;

pub use connection::DbConnection;
pub use query::{DeleteQuery, QueryBuilder, SelectQuery};
pub use table::{ColumnDef, FieldRef, Fts5Table, Op, Order, Table};
