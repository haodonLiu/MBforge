//! Benchmark for SqliteVectorStore brute-force cosine search.
//!
//! Run with: `cargo bench --bench vector_search`
//!
//! This produces hard numbers for the "<20K chunks, <10ms" claim in
//! `sqlite_vector_store.rs`. If numbers materially exceed the claim,
//! ANN (e.g. zvec) becomes worth re-evaluating.

use std::path::PathBuf;

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion, Throughput};
use mbforge::core::vector::sqlite_vector_store::SqliteVectorStore;

const DIM: usize = 1024;
const SIZES: &[usize] = &[1_000, 5_000, 10_000, 20_000, 50_000];

fn random_vector(dim: usize) -> Vec<f32> {
    use rand::Rng;
    let mut rng = rand::thread_rng();
    (0..dim).map(|_| rng.gen_range(-1.0f32..1.0f32)).collect()
}

fn normalize(v: &mut [f32]) {
    let norm: f32 = v.iter().map(|x| x * x).sum::<f32>().sqrt();
    if norm > 0.0 {
        for x in v.iter_mut() {
            *x /= norm;
        }
    }
}

fn bench_search(c: &mut Criterion) {
    let mut group = c.benchmark_group("sqlite_vector_search");

    for &size in SIZES {
        let temp_dir = tempfile::tempdir().expect("tempdir");
        let db_path: PathBuf = temp_dir.path().join("vectors.db");
        let store = SqliteVectorStore::open(&db_path, DIM).expect("open store");

        let chunk_ids: Vec<String> = (0..size).map(|i| format!("chunk-{i}")).collect();
        let texts: Vec<String> = (0..size).map(|i| format!("text {i}")).collect();
        let metadatas: Vec<String> = (0..size).map(|_| "{}".to_string()).collect();
        let mut vectors: Vec<Vec<f32>> = (0..size).map(|_| random_vector(DIM)).collect();
        for v in vectors.iter_mut() {
            normalize(v);
        }

        store
            .upsert_vectors(&chunk_ids, "doc1", &texts, &metadatas, &vectors)
            .expect("upsert");

        let query = {
            let mut q = random_vector(DIM);
            normalize(&mut q);
            q
        };

        group.throughput(Throughput::Elements(size as u64));
        group.bench_with_input(BenchmarkId::from_parameter(size), &size, |b, &_size| {
            b.iter(|| {
                let results = store
                    .search_vector(&query, 10, None)
                    .expect("search");
                assert!(!results.is_empty());
            });
        });
    }

    group.finish();
}

criterion_group!(benches, bench_search);
criterion_main!(benches);
