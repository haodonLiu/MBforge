#![allow(clippy::new_ret_no_self, clippy::unused_self, dead_code)]

//! Compile-time stub for `zvec-bindings`.
//!
//! This stub provides the same public API surface used by `mbforge-domain`
//! so that `cargo check` / `cargo test` can pass in environments without the
//! Zvec C++ toolchain (CMake + MSVC/GCC). It returns empty/no-op results.
//!
//! Replace this stub with the real `zvec-bindings` crate (version 0.4,
//! feature `sync`) once the build environment has the required C++ tools.

use std::path::Path;

pub type Result<T> = std::result::Result<T, String>;

/// Vector distance metric.
#[derive(Debug, Clone, Copy)]
pub enum MetricType {
    Cosine,
}

/// A Zvec collection schema.
#[derive(Debug, Clone, Default)]
pub struct CollectionSchema {
    _name: String,
}

impl CollectionSchema {
    pub fn builder(name: &str) -> Result<CollectionSchemaBuilder> {
        CollectionSchemaBuilder::new(name)
    }
}

/// Builder for `CollectionSchema`.
#[derive(Debug, Clone, Default)]
pub struct CollectionSchemaBuilder {
    _name: String,
}

impl CollectionSchemaBuilder {
    pub fn new(name: &str) -> Result<Self> {
        Ok(Self {
            _name: name.to_string(),
        })
    }

    pub fn builder(name: &str) -> Result<Self> {
        Self::new(name)
    }

    pub fn field(&mut self, _field: FieldSchema) -> Result<&mut Self> {
        Ok(self)
    }

    pub fn build(&self) -> Result<CollectionSchema> {
        Ok(CollectionSchema {
            _name: self._name.clone(),
        })
    }
}

/// A field schema.
#[derive(Debug, Clone, Default)]
pub struct FieldSchema {
    _name: String,
}

impl FieldSchema {
    pub fn string(name: &str) -> FieldSchema {
        Self {
            _name: name.to_string(),
        }
    }

    pub fn primary_key(self, _primary: bool) -> Self {
        self
    }

    pub fn invert_index(self, _enable: bool, _realtime: bool) -> Self {
        self
    }

    pub fn fts_tokenizer(self, _tokenizer: &str) -> Self {
        self
    }

    pub fn vector_fp32(name: &str, _dim: usize) -> FieldSchema {
        Self {
            _name: name.to_string(),
        }
    }

    pub fn hnsw(self, _m: usize, _ef: usize) -> Self {
        self
    }

    pub fn metric(self, _metric: MetricType) -> Self {
        self
    }
}

/// A document to insert.
#[derive(Debug, Clone, Default)]
pub struct Doc {
    _id: String,
}

impl Doc {
    pub fn id(id: &str) -> Self {
        Self {
            _id: id.to_string(),
        }
    }

    pub fn add_string(&mut self, _field: &str, _value: &str) -> Result<()> {
        Ok(())
    }

    pub fn add_vector_fp32(&mut self, _field: &str, _value: &[f32]) -> Result<()> {
        Ok(())
    }
}

/// A thread-safe Zvec collection handle.
#[derive(Debug, Clone, Default)]
pub struct SharedCollection;

impl SharedCollection {
    pub fn insert(&self, _docs: &[Doc]) -> Result<()> {
        Ok(())
    }

    pub fn delete_by_filter(&self, _filter: &str) -> Result<()> {
        Ok(())
    }

    pub fn query<Q: Query>(&self, _query: &Q) -> Result<QueryResults> {
        Ok(QueryResults { results: vec![] })
    }

    pub fn count(&self) -> Result<usize> {
        Ok(0)
    }
}

/// Trait for query types accepted by `SharedCollection::query`.
pub trait Query {}

/// Vector query.
#[derive(Debug, Clone, Default)]
pub struct VectorQuery;

impl Query for VectorQuery {}

impl VectorQuery {
    pub fn builder() -> VectorQueryBuilder {
        VectorQueryBuilder
    }

    pub fn filter(self, _filter: &str) -> Self {
        self
    }
}

/// Builder for `VectorQuery`.
#[derive(Debug, Clone, Default)]
pub struct VectorQueryBuilder;

impl VectorQueryBuilder {
    pub fn field(self, _field: &str) -> Self {
        self
    }

    pub fn vector_fp32(self, _vector: &[f32]) -> Self {
        self
    }

    pub fn topk(self, _topk: usize) -> Self {
        self
    }

    pub fn build(self) -> Result<VectorQuery> {
        Ok(VectorQuery)
    }
}

/// Full-text search query.
#[derive(Debug, Clone, Default)]
pub struct FtsQuery;

impl Query for FtsQuery {}

impl FtsQuery {
    pub fn new(_field: &str, _query: &str, _topk: usize, _filter: Option<&str>) -> Result<Self> {
        Ok(Self)
    }
}

/// Multi-query (fusion) request.
#[derive(Debug, Clone, Default)]
pub struct MultiQuery;

impl Query for MultiQuery {}

impl MultiQuery {
    pub fn new(_queries: Vec<Box<dyn Query>>) -> MultiQueryBuilder {
        MultiQueryBuilder
    }
}

/// Builder for `MultiQuery`.
#[derive(Debug, Clone, Default)]
pub struct MultiQueryBuilder;

impl MultiQueryBuilder {
    pub fn reranker(self, _reranker: RrfReranker) -> Result<MultiQuery> {
        Ok(MultiQuery)
    }
}

/// RRF reranker config.
#[derive(Debug, Clone, Default)]
pub struct RrfReranker {
    _top_n: usize,
}

impl RrfReranker {
    pub fn with_top_n(top_n: usize) -> Self {
        Self { _top_n: top_n }
    }
}

/// A single search result row.
#[derive(Debug, Clone, Default)]
pub struct SearchResult {
    _id: String,
}

impl SearchResult {
    pub fn pk(&self) -> &str {
        &self._id
    }

    pub fn field_as_string(&self, _field: &str) -> Option<String> {
        None
    }

    pub fn score(&self) -> f32 {
        0.0
    }
}

/// Collection of search results returned by `SharedCollection::query`.
#[derive(Debug, Clone, Default)]
pub struct QueryResults {
    results: Vec<SearchResult>,
}

impl QueryResults {
    pub fn iter(&self) -> std::slice::Iter<'_, SearchResult> {
        self.results.iter()
    }
}

/// Open or create a shared collection at `path`.
pub fn create_and_open_shared(
    _path: &Path,
    _schema: &CollectionSchema,
    _options: Option<()>,
) -> Result<SharedCollection> {
    Ok(SharedCollection)
}
