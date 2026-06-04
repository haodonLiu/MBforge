//! 数据库表 trait 定义
//!
//! 提供类型安全的 schema 定义，消除手写 SQL DDL 和 row.get(0) 按索引映射。

use rusqlite::{Row, ToSql};

/// 列定义
#[derive(Debug, Clone)]
pub struct ColumnDef {
    pub name: &'static str,
    pub sql_type: &'static str,
    pub primary_key: bool,
    pub not_null: bool,
    pub unique: bool,
    pub index: bool,
    pub default: Option<&'static str>,
    pub auto_increment: bool,
}

impl ColumnDef {
    pub const fn new(name: &'static str, sql_type: &'static str) -> Self {
        Self {
            name,
            sql_type,
            primary_key: false,
            not_null: false,
            unique: false,
            index: false,
            default: None,
            auto_increment: false,
        }
    }

    pub const fn primary_key(mut self) -> Self {
        self.primary_key = true;
        self
    }

    pub const fn not_null(mut self) -> Self {
        self.not_null = true;
        self
    }

    pub const fn nullable(mut self) -> Self {
        self.not_null = false;
        self
    }

    pub const fn unique(mut self) -> Self {
        self.unique = true;
        self
    }

    pub const fn index(mut self) -> Self {
        self.index = true;
        self
    }

    pub const fn default(mut self, val: &'static str) -> Self {
        self.default = Some(val);
        self
    }

    pub const fn auto_increment(mut self) -> Self {
        self.auto_increment = true;
        self
    }

    /// 生成列的 DDL 片段
    pub fn to_ddl(&self) -> String {
        let mut parts = vec![format!("{} {}", self.name, self.sql_type)];
        if self.primary_key {
            parts.push("PRIMARY KEY".to_string());
            if self.auto_increment {
                parts.push("AUTOINCREMENT".to_string());
            }
        } else if self.not_null {
            parts.push("NOT NULL".to_string());
        }
        if self.unique && !self.primary_key {
            parts.push("UNIQUE".to_string());
        }
        if let Some(val) = self.default {
            parts.push(format!("DEFAULT {}", val));
        }
        parts.join(" ")
    }
}

/// 数据库表 trait
pub trait Table: Sized {
    fn table_name() -> &'static str;
    fn columns() -> Vec<ColumnDef>;
    fn from_row(row: &Row) -> Result<Self, String>;
    fn to_params(&self) -> Vec<Box<dyn ToSql + '_>>;

    /// CREATE TABLE IF NOT EXISTS DDL
    fn ddl_sql() -> String {
        let cols: Vec<String> = Self::columns().iter().map(|c| c.to_ddl()).collect();
        format!(
            "CREATE TABLE IF NOT EXISTS {} (\n  {}\n)",
            Self::table_name(),
            cols.join(",\n  ")
        )
    }

    /// CREATE INDEX IF NOT EXISTS 语句
    fn index_sqls() -> Vec<String> {
        Self::columns()
            .iter()
            .filter(|c| c.index && !c.primary_key)
            .map(|c| {
                format!(
                    "CREATE INDEX IF NOT EXISTS idx_{}_{} ON {}({})",
                    Self::table_name(),
                    c.name,
                    Self::table_name(),
                    c.name
                )
            })
            .collect()
    }

    /// 列名 CSV
    fn columns_csv() -> String {
        Self::columns().iter().map(|c| c.name).collect::<Vec<_>>().join(", ")
    }

    /// 占位符 CSV
    fn placeholders_csv() -> String {
        let count = Self::columns().len();
        (1..=count).map(|i| format!("?{}", i)).collect::<Vec<_>>().join(", ")
    }
}

/// FTS5 虚拟表 trait
pub trait Fts5Table {
    fn table_name() -> &'static str;
    fn indexed_columns() -> Vec<&'static str>;
    fn content_table() -> &'static str;
    fn content_rowid() -> &'static str;

    fn ddl_sql() -> String {
        let cols = Self::indexed_columns().join(", ");
        format!(
            "CREATE VIRTUAL TABLE IF NOT EXISTS {} USING fts5(\n  {},\n  content='{}',\n  content_rowid='{}'\n)",
            Self::table_name(),
            cols,
            Self::content_table(),
            Self::content_rowid()
        )
    }

    fn sync_insert_sql() -> String {
        let cols = Self::indexed_columns().join(", ");
        let placeholders: Vec<String> = (1..=Self::indexed_columns().len())
            .map(|i| format!("?{}", i))
            .collect();
        format!("INSERT INTO {} ({}) VALUES ({})", Self::table_name(), cols, placeholders.join(", "))
    }

    fn sync_delete_sql() -> String {
        format!("DELETE FROM {} WHERE rowid = ?1", Self::table_name())
    }
}

/// 字段引用 — 用于类型安全的 WHERE 条件
#[derive(Debug, Clone)]
pub struct FieldRef {
    pub name: &'static str,
}

impl FieldRef {
    pub const fn new(name: &'static str) -> Self {
        Self { name }
    }
}

/// WHERE 操作符
#[derive(Debug, Clone)]
pub enum Op {
    Eq,
    Ne,
    Gt,
    Lt,
    Gte,
    Lte,
    Like,
    In,
    IsNull,
    IsNotNull,
}

impl Op {
    pub fn sql(&self) -> &'static str {
        match self {
            Op::Eq => "=",
            Op::Ne => "!=",
            Op::Gt => ">",
            Op::Lt => "<",
            Op::Gte => ">=",
            Op::Lte => "<=",
            Op::Like => "LIKE",
            Op::In => "IN",
            Op::IsNull => "IS NULL",
            Op::IsNotNull => "IS NOT NULL",
        }
    }
}

/// 排序方向
#[derive(Debug, Clone)]
pub enum Order {
    Asc,
    Desc,
}

impl Order {
    pub fn sql(&self) -> &'static str {
        match self {
            Order::Asc => "ASC",
            Order::Desc => "DESC",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_column_def_ddl() {
        let col = ColumnDef::new("id", "TEXT").primary_key();
        assert_eq!(col.to_ddl(), "id TEXT PRIMARY KEY");

        let col = ColumnDef::new("name", "TEXT").not_null();
        assert_eq!(col.to_ddl(), "name TEXT NOT NULL");

        let col = ColumnDef::new("score", "REAL").nullable().default("0.0");
        assert_eq!(col.to_ddl(), "score REAL DEFAULT 0.0");

        let col = ColumnDef::new("id", "INTEGER").primary_key().auto_increment();
        assert_eq!(col.to_ddl(), "id INTEGER PRIMARY KEY AUTOINCREMENT");
    }

    #[test]
    fn test_op_sql() {
        assert_eq!(Op::Eq.sql(), "=");
        assert_eq!(Op::Like.sql(), "LIKE");
        assert_eq!(Op::IsNull.sql(), "IS NULL");
    }
}
