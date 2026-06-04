//! 数据库连接管理
//!
//! 封装 rusqlite::Connection，提供统一的表注册和查询接口。

use std::path::Path;
use std::sync::Mutex;

use rusqlite::{Connection, ToSql};

use super::migration::MigrationSet;
use super::table::{Fts5Table, Table};

/// 数据库连接
pub struct DbConnection {
    conn: Mutex<Connection>,
}

impl DbConnection {
    /// 打开数据库连接
    pub fn open(path: &Path) -> Result<Self, String> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("Create DB dir failed: {}", e))?;
        }

        let conn = Connection::open(path)
            .map_err(|e| format!("Open DB failed: {}", e))?;

        conn.execute_batch(
            "PRAGMA journal_mode=WAL;
             PRAGMA foreign_keys=ON;
             PRAGMA busy_timeout=5000;",
        )
        .map_err(|e| format!("Set pragma failed: {}", e))?;

        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    /// 从已有的 Connection 创建
    pub fn from_conn(conn: Connection) -> Result<Self, String> {
        conn.execute_batch(
            "PRAGMA journal_mode=WAL;
             PRAGMA foreign_keys=ON;
             PRAGMA busy_timeout=5000;",
        )
        .map_err(|e| format!("Set pragma failed: {}", e))?;

        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    /// 注册表结构
    pub fn register<T: Table>(&self) -> Result<(), String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        let ddl = T::ddl_sql();
        conn.execute(&ddl, [])
            .map_err(|e| format!("Create table {} failed: {}", T::table_name(), e))?;

        for idx_sql in T::index_sqls() {
            conn.execute(&idx_sql, [])
                .map_err(|e| format!("Create index on {} failed: {}", T::table_name(), e))?;
        }

        log::info!("Registered table: {}", T::table_name());
        Ok(())
    }

    /// 注册表结构 + 迁移
    pub fn register_with_migrations<T: Table>(&self, migrations: &MigrationSet) -> Result<(), String> {
        self.register::<T>()?;
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        migrations.run(&conn)?;
        Ok(())
    }

    /// 注册 FTS5 虚拟表
    pub fn register_fts5<T: Fts5Table>(&self) -> Result<(), String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        let ddl = T::ddl_sql();
        conn.execute(&ddl, [])
            .map_err(|e| format!("Create FTS5 {} failed: {}", T::table_name(), e))?;
        log::info!("Registered FTS5 table: {}", T::table_name());
        Ok(())
    }

    /// 执行原始 SQL
    pub fn execute(&self, sql: &str, params: &[&dyn ToSql]) -> Result<usize, String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        conn.execute(sql, params)
            .map_err(|e| format!("Execute failed: {}", e))
    }

    /// 原始查询
    pub fn query_raw<T, F>(
        &self,
        sql: &str,
        params: &[&dyn ToSql],
        mapper: F,
    ) -> Result<Vec<T>, String>
    where
        F: FnMut(&rusqlite::Row) -> Result<T, rusqlite::Error>,
    {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        let mut stmt = conn
            .prepare(sql)
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let rows = stmt
            .query_map(params, mapper)
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        for row in rows {
            results.push(row.map_err(|e| format!("Row error: {}", e))?);
        }
        Ok(results)
    }

    /// 类型安全查询
    pub fn query<T: Table>(&self) -> super::query::QueryBuilder<T> {
        super::query::QueryBuilder::new(self)
    }

    /// 获取底层连接
    pub fn raw_conn(&self) -> &Mutex<Connection> {
        &self.conn
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::table::ColumnDef;

    struct TestRow {
        pub id: String,
        pub name: String,
    }

    impl Table for TestRow {
        fn table_name() -> &'static str { "test_items" }
        fn columns() -> Vec<ColumnDef> {
            vec![
                ColumnDef::new("id", "TEXT").primary_key(),
                ColumnDef::new("name", "TEXT").not_null(),
            ]
        }
        fn from_row(row: &rusqlite::Row) -> Result<Self, String> {
            Ok(Self {
                id: row.get(0).map_err(|e| format!("id: {}", e))?,
                name: row.get(1).map_err(|e| format!("name: {}", e))?,
            })
        }
        fn to_params(&self) -> Vec<Box<dyn ToSql + '_>> {
            vec![Box::new(self.id.clone()), Box::new(self.name.clone())]
        }
    }

    #[test]
    fn test_db_connection_register() {
        let db = DbConnection::open_in_memory().unwrap();
        db.register::<TestRow>().unwrap();

        let count: i64 = db.raw_conn().lock().unwrap()
            .query_row("SELECT COUNT(*) FROM test_items", [], |r| r.get(0))
            .unwrap();
        assert_eq!(count, 0);
    }

    #[test]
    fn test_db_connection_insert_query() {
        let db = DbConnection::open_in_memory().unwrap();
        db.register::<TestRow>().unwrap();

        db.query::<TestRow>().insert(&TestRow {
            id: "1".into(),
            name: "test".into(),
        }).unwrap();

        let results = db.query::<TestRow>()
            .select()
            .fetch()
            .unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].name, "test");
    }

    impl DbConnection {
        fn open_in_memory() -> Result<Self, String> {
            let conn = Connection::open_in_memory()
                .map_err(|e| format!("Open memory DB failed: {}", e))?;
            conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")
                .map_err(|e| format!("Set pragma failed: {}", e))?;
            Ok(Self { conn: Mutex::new(conn) })
        }
    }
}
