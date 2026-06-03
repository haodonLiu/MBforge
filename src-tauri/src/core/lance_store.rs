//! LanceDB 向量存储 — 语义搜索
//!
//! 使用 LanceDB 嵌入式向量数据库存储 embedding，支持 ANN 近似最近邻搜索。
//! 与 SQLite FTS5 互补：FTS5 处理精确关键词匹配，LanceDB 处理语义相似度搜索。

use std::path::Path;
use std::sync::Arc;

use arrow::array::{Array, Float32Array, StringArray, FixedSizeListArray};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;
use futures::TryStreamExt;
use lancedb::connection::Connection;
use lancedb::query::{ExecutableQuery, QueryBase};
use lancedb::table::Table;

use super::vector_store::SearchResult;

/// LanceDB 向量存储
pub struct LanceVectorStore {
    db: Connection,
    table_name: String,
    dim: usize,
}

impl LanceVectorStore {
    /// 打开或创建 LanceDB 数据库
    pub async fn new(db_dir: &Path, dim: usize) -> Result<Self, String> {
        std::fs::create_dir_all(db_dir)
            .map_err(|e| format!("Failed to create LanceDB dir: {}", e))?;

        let db_path = db_dir.to_string_lossy().to_string();
        let db = lancedb::connect(&db_path)
            .execute()
            .await
            .map_err(|e| format!("LanceDB connect failed: {}", e))?;

        let table_name = "embeddings".to_string();

        // 如果表不存在则创建
        let tables = db
            .table_names()
            .execute()
            .await
            .map_err(|e| format!("LanceDB list tables failed: {}", e))?;

        if !tables.contains(&table_name) {
            Self::create_table(&db, &table_name, dim).await?;
        }

        Ok(Self {
            db,
            table_name,
            dim,
        })
    }

    /// 创建空的 embeddings 表
    async fn create_table(db: &Connection, table_name: &str, dim: usize) -> Result<(), String> {
        let schema = Arc::new(Schema::new(vec![
            Field::new("chunk_id", DataType::Utf8, false),
            Field::new("doc_id", DataType::Utf8, false),
            Field::new("text", DataType::Utf8, false),
            Field::new("metadata", DataType::Utf8, false),
            Field::new(
                "vector",
                DataType::FixedSizeList(
                    Arc::new(Field::new("item", DataType::Float32, true)),
                    dim as i32,
                ),
                false,
            ),
        ]));

        // 创建空表：用一个空 batch
        let batch = RecordBatch::new_empty(schema);
        db.create_table(table_name, vec![batch])
            .execute()
            .await
            .map_err(|e| format!("LanceDB create table failed: {}", e))?;

        Ok(())
    }

    /// 写入向量数据（upsert 语义：先删旧的再加新的）
    pub async fn upsert_vectors(
        &self,
        chunk_ids: &[String],
        doc_id: &str,
        texts: &[String],
        metadatas: &[String],
        vectors: &[Vec<f32>],
    ) -> Result<(), String> {
        if chunk_ids.is_empty() {
            return Ok(());
        }

        let table = self
            .db
            .open_table(&self.table_name)
            .execute()
            .await
            .map_err(|e| format!("LanceDB open table failed: {}", e))?;

        // 先删除该 doc_id 的旧数据
        table
            .delete(&format!("doc_id = '{}'", doc_id.replace('\'', "''")))
            .await
            .map_err(|e| format!("LanceDB delete failed: {}", e))?;

        // 构建 RecordBatch
        let vector_field = Arc::new(Field::new("item", DataType::Float32, true));
        let schema = Arc::new(Schema::new(vec![
            Field::new("chunk_id", DataType::Utf8, false),
            Field::new("doc_id", DataType::Utf8, false),
            Field::new("text", DataType::Utf8, false),
            Field::new("metadata", DataType::Utf8, false),
            Field::new(
                "vector",
                DataType::FixedSizeList(vector_field.clone(), self.dim as i32),
                false,
            ),
        ]));

        let chunk_id_arr = Arc::new(StringArray::from(chunk_ids.to_vec()));
        let doc_id_arr = Arc::new(StringArray::from(vec![doc_id; chunk_ids.len()]));
        let text_arr = Arc::new(StringArray::from(texts.to_vec()));
        let meta_arr = Arc::new(StringArray::from(metadatas.to_vec()));

        // 扁平化所有向量为一个 Float32Array
        let flat: Vec<f32> = vectors.iter().flat_map(|v| v.iter().copied()).collect();
        let values: Arc<dyn Array> = Arc::new(Float32Array::from(flat));
        let vector_arr = FixedSizeListArray::try_new(vector_field, self.dim as i32, values, None)
            .map_err(|e| format!("FixedSizeListArray failed: {}", e))?;

        let batch = RecordBatch::try_new(
            schema,
            vec![
                chunk_id_arr,
                doc_id_arr,
                text_arr,
                meta_arr,
                Arc::new(vector_arr),
            ],
        )
        .map_err(|e| format!("RecordBatch creation failed: {}", e))?;

        table
            .add(vec![batch])
            .execute()
            .await
            .map_err(|e| format!("LanceDB add failed: {}", e))?;

        Ok(())
    }

    /// 向量搜索：返回与 query_embedding 最相似的 top_k 条结果
    pub async fn search_vector(
        &self,
        query_embedding: &[f32],
        top_k: usize,
        filter_doc_id: Option<&str>,
    ) -> Result<Vec<SearchResult>, String> {
        let table = self
            .db
            .open_table(&self.table_name)
            .execute()
            .await
            .map_err(|e| format!("LanceDB open table failed: {}", e))?;

        let query = table
            .vector_search(query_embedding.to_vec())
            .map_err(|e| format!("vector_search failed: {}", e))?
            .limit(top_k);

        let query = if let Some(doc_id) = filter_doc_id {
            query.only_if(format!("doc_id = '{}'", doc_id.replace('\'', "''")))
        } else {
            query
        };

        let results = query
            .execute()
            .await
            .map_err(|e| format!("LanceDB vector search failed: {}", e))?;

        // 解析结果
        let batches: Vec<RecordBatch> = results
            .try_collect::<Vec<RecordBatch>>()
            .await
            .map_err(|e| format!("LanceDB collect results failed: {}", e))?;

        let mut search_results = Vec::new();

        for batch in &batches {
            let col_chunk_id: &Arc<dyn Array> = batch
                .column_by_name("chunk_id")
                .ok_or("Missing chunk_id column")?;
            let chunk_ids = col_chunk_id
                .as_any()
                .downcast_ref::<StringArray>()
                .ok_or("chunk_id is not StringArray")?;

            let col_text: &Arc<dyn Array> = batch
                .column_by_name("text")
                .ok_or("Missing text column")?;
            let texts = col_text
                .as_any()
                .downcast_ref::<StringArray>()
                .ok_or("text is not StringArray")?;

            let col_meta: &Arc<dyn Array> = batch
                .column_by_name("metadata")
                .ok_or("Missing metadata column")?;
            let metadatas = col_meta
                .as_any()
                .downcast_ref::<StringArray>()
                .ok_or("metadata is not StringArray")?;

            // _distance 列由 vector_search 自动添加
            let distances: Option<&Float32Array> = batch
                .column_by_name("_distance")
                .and_then(|c: &Arc<dyn Array>| c.as_any().downcast_ref::<Float32Array>());

            for i in 0..batch.num_rows() {
                let distance = distances.map(|d| d.value(i)).unwrap_or(0.0);
                // 将距离转换为相似度分数 (0-1)，L2 距离越小越好
                let score = 1.0 / (1.0 + distance);

                let metadata: serde_json::Value =
                    serde_json::from_str(metadatas.value(i)).unwrap_or(serde_json::json!({}));

                search_results.push(SearchResult {
                    id: chunk_ids.value(i).to_string(),
                    text: texts.value(i).to_string(),
                    metadata,
                    score,
                });
            }
        }

        Ok(search_results)
    }

    /// 删除指定文档的所有向量
    pub async fn delete_doc(&self, doc_id: &str) -> Result<(), String> {
        let table = self
            .db
            .open_table(&self.table_name)
            .execute()
            .await
            .map_err(|e| format!("LanceDB open table failed: {}", e))?;

        table
            .delete(&format!("doc_id = '{}'", doc_id.replace('\'', "''")))
            .await
            .map_err(|e| format!("LanceDB delete failed: {}", e))?;

        Ok(())
    }

    /// 向量数量
    pub async fn count(&self) -> Result<usize, String> {
        let table = self
            .db
            .open_table(&self.table_name)
            .execute()
            .await
            .map_err(|e| format!("LanceDB open table failed: {}", e))?;

        let count = table
            .count_rows(None)
            .await
            .map_err(|e| format!("LanceDB count failed: {}", e))?;

        Ok(count)
    }

    /// 创建全文搜索索引（BM25），用于混合搜索
    pub async fn create_fts_index(&self) -> Result<(), String> {
        let table = self
            .db
            .open_table(&self.table_name)
            .execute()
            .await
            .map_err(|e| format!("LanceDB open table failed: {}", e))?;

        table
            .create_index(&["text"], lancedb::index::Index::FTS(Default::default()))
            .execute()
            .await
            .map_err(|e| format!("LanceDB create FTS index failed: {}", e))?;

        log::info!("LanceDB: FTS index created on '{}' table", self.table_name);
        Ok(())
    }

    /// 纯文本搜索（BM25）
    pub async fn search_text(
        &self,
        query: &str,
        top_k: usize,
        filter_doc_id: Option<&str>,
    ) -> Result<Vec<SearchResult>, String> {
        use lancedb::index::scalar::FullTextSearchQuery;

        let table = self
            .db
            .open_table(&self.table_name)
            .execute()
            .await
            .map_err(|e| format!("LanceDB open table failed: {}", e))?;

        let mut q = table
            .query()
            .full_text_search(FullTextSearchQuery::new(query.to_string()))
            .limit(top_k);

        if let Some(doc_id) = filter_doc_id {
            q = q.only_if(format!("doc_id = '{}'", doc_id.replace('\'', "''")));
        }

        let results = q
            .execute()
            .await
            .map_err(|e| format!("LanceDB FTS search failed: {}", e))?;

        let batches: Vec<RecordBatch> = results
            .try_collect()
            .await
            .map_err(|e| format!("LanceDB collect results failed: {}", e))?;

        self.parse_search_results(&batches)
    }

    /// 混合搜索：向量 + BM25 原生融合（替代手动 RRF）
    pub async fn search_hybrid(
        &self,
        query_text: &str,
        query_embedding: &[f32],
        top_k: usize,
        filter_doc_id: Option<&str>,
    ) -> Result<Vec<SearchResult>, String> {
        use lancedb::index::scalar::FullTextSearchQuery;

        let table = self
            .db
            .open_table(&self.table_name)
            .execute()
            .await
            .map_err(|e| format!("LanceDB open table failed: {}", e))?;

        let mut q = table
            .vector_search(query_embedding.to_vec())
            .map_err(|e| format!("vector_search failed: {}", e))?
            .full_text_search(FullTextSearchQuery::new(query_text.to_string()))
            .limit(top_k);

        if let Some(doc_id) = filter_doc_id {
            q = q.only_if(format!("doc_id = '{}'", doc_id.replace('\'', "''")));
        }

        let options = lancedb::query::QueryExecutionOptions::default();
        let results = q
            .execute_hybrid(options)
            .await
            .map_err(|e| format!("LanceDB hybrid search failed: {}", e))?;

        let batches: Vec<RecordBatch> = results
            .try_collect()
            .await
            .map_err(|e| format!("LanceDB collect results failed: {}", e))?;

        self.parse_search_results(&batches)
    }

    /// 解析 RecordBatch 为 SearchResult（内部辅助方法）
    fn parse_search_results(&self, batches: &[RecordBatch]) -> Result<Vec<SearchResult>, String> {
        let mut search_results = Vec::new();

        for batch in batches {
            let col_chunk_id: &Arc<dyn Array> = batch
                .column_by_name("chunk_id")
                .ok_or("Missing chunk_id column")?;
            let chunk_ids = col_chunk_id
                .as_any()
                .downcast_ref::<StringArray>()
                .ok_or("chunk_id is not StringArray")?;

            let col_text: &Arc<dyn Array> = batch
                .column_by_name("text")
                .ok_or("Missing text column")?;
            let texts = col_text
                .as_any()
                .downcast_ref::<StringArray>()
                .ok_or("text is not StringArray")?;

            let col_meta: &Arc<dyn Array> = batch
                .column_by_name("metadata")
                .ok_or("Missing metadata column")?;
            let metadatas = col_meta
                .as_any()
                .downcast_ref::<StringArray>()
                .ok_or("metadata is not StringArray")?;

            // _distance 列由 vector_search 自动添加
            let distances: Option<&Float32Array> = batch
                .column_by_name("_distance")
                .and_then(|c: &Arc<dyn Array>| c.as_any().downcast_ref::<Float32Array>());

            // _score 列由 hybrid search 添加
            let scores: Option<&Float32Array> = batch
                .column_by_name("_score")
                .and_then(|c: &Arc<dyn Array>| c.as_any().downcast_ref::<Float32Array>());

            for i in 0..batch.num_rows() {
                let score = if let Some(s) = scores {
                    s.value(i)
                } else if let Some(d) = distances {
                    1.0 / (1.0 + d.value(i))
                } else {
                    1.0
                };

                let metadata: serde_json::Value =
                    serde_json::from_str(metadatas.value(i)).unwrap_or(serde_json::json!({}));

                search_results.push(SearchResult {
                    id: chunk_ids.value(i).to_string(),
                    text: texts.value(i).to_string(),
                    metadata,
                    score,
                });
            }
        }

        Ok(search_results)
    }
}

