use pyo3::prelude::*;

mod tanimoto;

/// MBForge 核心加速模块
///
/// 提供高性能计算加速，用于分子指纹相似度计算等场景。
/// 如果未安装 Rust 模块，Python 端会自动回退到纯 Python 实现。
#[pymodule]
fn mbforge_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(tanimoto::pairwise_tanimoto_matrix, m)?)?;
    Ok(())
}
