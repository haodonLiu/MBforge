//! 类型安全查询构造器
//!
//! Builder 模式的 SELECT / INSERT / DELETE 查询。

use std::marker::PhantomData;
use std::sync::Arc;

use rusqlite::ToSql;

use super::connection::DbConnection;
use super::table::{FieldRef, Op, Order, Table};

/// 查询入口
pub struct QueryBuilder<'a, T: Table> {
    conn: &'a DbConnection,
    _phantom: PhantomData<T>,
}

impl<'a, T: Table> QueryBuilder<'a, T> {
    pub fn new(conn: &'a DbConnection) -> Self {
        Self {
            conn,
            _phantom: PhantomData,
        }
    }

    /// SELECT 查询
    pub fn select(self) -> SelectQuery<'a, T> {
        SelectQuery::new(self.conn)
    }

    /// INSERT OR REPLACE
    pub fn insert(&self, record: &T) -> Result<usize, String> {
        let sql = format!(
            "INSERT OR REPLACE INTO {} ({}) VALUES ({})",
            T::table_name(),
            T::columns_csv(),
            T::placeholders_csv()
        );

        let params = record.to_params();
        let params_ref: Vec<&dyn ToSql> = params.iter().map(|p| p.as_ref()).collect();

        let conn = self.conn.raw_conn().lock().map_err(|e| format!("Lock error: {}", e))?;
        conn.execute(&sql, params_ref.as_slice())
            .map_err(|e| format!("Insert into {} failed: {}", T::table_name(), e))
    }

    /// DELETE 查询
    pub fn delete(self) -> DeleteQuery<'a, T> {
        DeleteQuery::new(self.conn)
    }
}

/// SELECT 查询 builder
pub struct SelectQuery<'a, T: Table> {
    conn: &'a DbConnection,
    where_clauses: Vec<String>,
    params: Vec<Arc<dyn ToSql + 'a>>,
    order: Option<String>,
    limit_val: Option<usize>,
    offset_val: Option<usize>,
    _phantom: PhantomData<T>,
}

impl<'a, T: Table> SelectQuery<'a, T> {
    fn new(conn: &'a DbConnection) -> Self {
        Self {
            conn,
            where_clauses: Vec::new(),
            params: Vec::new(),
            order: None,
            limit_val: None,
            offset_val: None,
            _phantom: PhantomData,
        }
    }

    /// WHERE field op value
    pub fn where_<V: ToSql + 'a>(mut self, field: FieldRef, op: Op, value: V) -> Self {
        if matches!(op, Op::IsNull | Op::IsNotNull) {
            self.where_clauses.push(format!("{} {}", field.name, op.sql()));
        } else {
            self.where_clauses.push(format!("{} {} ?{}", field.name, op.sql(), self.params.len() + 1));
            self.params.push(Arc::new(value));
        }
        self
    }

    /// ORDER BY
    pub fn order_by(mut self, field: FieldRef, dir: Order) -> Self {
        self.order = Some(format!("{} {}", field.name, dir.sql()));
        self
    }

    /// LIMIT
    pub fn limit(mut self, n: usize) -> Self {
        self.limit_val = Some(n);
        self
    }

    /// OFFSET
    pub fn offset(mut self, n: usize) -> Self {
        self.offset_val = Some(n);
        self
    }

    /// 执行查询，返回 Vec<T>
    pub fn fetch(self) -> Result<Vec<T>, String> {
        let mut sql = format!("SELECT * FROM {}", T::table_name());
        if !self.where_clauses.is_empty() {
            sql.push_str(&format!(" WHERE {}", self.where_clauses.join(" AND ")));
        }
        if let Some(ref o) = self.order {
            sql.push_str(&format!(" ORDER BY {}", o));
        }
        if let Some(l) = self.limit_val {
            sql.push_str(&format!(" LIMIT {}", l));
        }
        if let Some(o) = self.offset_val {
            sql.push_str(&format!(" OFFSET {}", o));
        }

        let params_ref: Vec<&dyn ToSql> = self.params.iter().map(|p| p.as_ref()).collect();

        let conn = self.conn.raw_conn().lock().map_err(|e| format!("Lock error: {}", e))?;
        let mut stmt = conn.prepare(&sql).map_err(|e| format!("Prepare failed: {}", e))?;

        let rows = stmt
            .query_map(params_ref.as_slice(), T::from_row)
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        for row in rows {
            results.push(row.map_err(|e| format!("Row error: {}", e))?);
        }
        Ok(results)
    }

    /// 执行查询，返回第一条
    pub fn fetch_one(self) -> Result<Option<T>, String> {
        let mut results = self.limit(1).fetch()?;
        Ok(results.pop())
    }

    /// 执行查询，返回数量
    pub fn count(self) -> Result<usize, String> {
        let mut sql = format!("SELECT COUNT(*) FROM {}", T::table_name());
        if !self.where_clauses.is_empty() {
            sql.push_str(&format!(" WHERE {}", self.where_clauses.join(" AND ")));
        }

        let params_ref: Vec<&dyn ToSql> = self.params.iter().map(|p| p.as_ref()).collect();

        let conn = self.conn.raw_conn().lock().map_err(|e| format!("Lock error: {}", e))?;
        let count: i64 = conn
            .query_row(&sql, params_ref.as_slice(), |row| row.get(0))
            .map_err(|e| format!("Count failed: {}", e))?;

        Ok(count as usize)
    }
}

/// DELETE 查询 builder
pub struct DeleteQuery<'a, T: Table> {
    conn: &'a DbConnection,
    where_clauses: Vec<String>,
    params: Vec<Arc<dyn ToSql + 'a>>,
    _phantom: PhantomData<T>,
}

impl<'a, T: Table> DeleteQuery<'a, T> {
    fn new(conn: &'a DbConnection) -> Self {
        Self {
            conn,
            where_clauses: Vec::new(),
            params: Vec::new(),
            _phantom: PhantomData,
        }
    }

    /// WHERE field op value
    pub fn where_<V: ToSql + 'a>(mut self, field: FieldRef, op: Op, value: V) -> Self {
        self.where_clauses.push(format!("{} {} ?{}", field.name, op.sql(), self.params.len() + 1));
        self.params.push(Arc::new(value));
        self
    }

    /// 执行删除
    pub fn execute(self) -> Result<usize, String> {
        let mut sql = format!("DELETE FROM {}", T::table_name());
        if !self.where_clauses.is_empty() {
            sql.push_str(&format!(" WHERE {}", self.where_clauses.join(" AND ")));
        }

        let params_ref: Vec<&dyn ToSql> = self.params.iter().map(|p| p.as_ref()).collect();

        let conn = self.conn.raw_conn().lock().map_err(|e| format!("Lock error: {}", e))?;
        conn.execute(&sql, params_ref.as_slice())
            .map_err(|e| format!("Delete from {} failed: {}", T::table_name(), e))
    }
}
