//! 数据库迁移系统
//!
//! 版本化的 schema 迁移，自动维护 _migrations 表。

use rusqlite::Connection;

/// 单个迁移
#[derive(Debug, Clone)]
pub struct Migration {
    pub version: u32,
    pub name: &'static str,
    pub up: &'static str,
}

/// 迁移集合
#[derive(Debug, Clone)]
pub struct MigrationSet {
    pub table_name: &'static str,
    pub migrations: Vec<Migration>,
}

impl MigrationSet {
    pub const fn new(table_name: &'static str) -> Self {
        Self {
            table_name,
            migrations: Vec::new(),
        }
    }

    pub fn add(mut self, migration: Migration) -> Self {
        self.migrations.push(migration);
        self
    }

    /// 执行所有 pending 迁移
    pub fn run(&self, conn: &Connection) -> Result<(), String> {
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations (
                table_name TEXT NOT NULL,
                version INTEGER NOT NULL,
                name TEXT NOT NULL,
                applied_at REAL NOT NULL,
                PRIMARY KEY (table_name, version)
            )",
            [],
        )
        .map_err(|e| format!("Create _migrations failed: {}", e))?;

        let current_version: u32 = conn
            .query_row(
                "SELECT COALESCE(MAX(version), 0) FROM _migrations WHERE table_name = ?1",
                rusqlite::params![self.table_name],
                |row| row.get(0),
            )
            .map_err(|e| format!("Query migration version failed: {}", e))?;

        for migration in &self.migrations {
            if migration.version > current_version {
                log::info!(
                    "Migration {}.{}: v{} → v{}",
                    self.table_name,
                    migration.name,
                    current_version,
                    migration.version
                );

                for stmt in migration.up.split(';').map(|s| s.trim()).filter(|s| !s.is_empty()) {
                    conn.execute(stmt, [])
                        .map_err(|e| format!("Migration {}.{} failed: {}", self.table_name, migration.name, e))?;
                }

                let now = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_secs_f64())
                    .unwrap_or(0.0);

                conn.execute(
                    "INSERT INTO _migrations (table_name, version, name, applied_at) VALUES (?1, ?2, ?3, ?4)",
                    rusqlite::params![self.table_name, migration.version, migration.name, now],
                )
                .map_err(|e| format!("Record migration failed: {}", e))?;
            }
        }

        Ok(())
    }

    /// 获取当前已应用的版本
    pub fn current_version(conn: &Connection, table_name: &str) -> Result<u32, String> {
        let table_exists: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='_migrations'",
                [],
                |row| row.get::<_, i64>(0),
            )
            .map(|n| n > 0)
            .unwrap_or(false);

        if !table_exists {
            return Ok(0);
        }

        conn.query_row(
            "SELECT COALESCE(MAX(version), 0) FROM _migrations WHERE table_name = ?1",
            rusqlite::params![table_name],
            |row| row.get(0),
        )
        .map_err(|e| format!("Query version failed: {}", e))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_migration_run() {
        let conn = Connection::open_in_memory().unwrap();
        let migrations = MigrationSet::new("test_table")
            .add(Migration {
                version: 1,
                name: "create",
                up: "CREATE TABLE test_table (id TEXT PRIMARY KEY, name TEXT)",
            })
            .add(Migration {
                version: 2,
                name: "add_column",
                up: "ALTER TABLE test_table ADD COLUMN score REAL DEFAULT 0.0",
            });

        migrations.run(&conn).unwrap();

        let version = MigrationSet::current_version(&conn, "test_table").unwrap();
        assert_eq!(version, 2);
    }

    #[test]
    fn test_migration_idempotent() {
        let conn = Connection::open_in_memory().unwrap();
        let migrations = MigrationSet::new("test_table")
            .add(Migration {
                version: 1,
                name: "create",
                up: "CREATE TABLE test_table (id TEXT PRIMARY KEY)",
            });

        migrations.run(&conn).unwrap();
        migrations.run(&conn).unwrap(); // 第二次运行不应报错

        let version = MigrationSet::current_version(&conn, "test_table").unwrap();
        assert_eq!(version, 1);
    }
}
