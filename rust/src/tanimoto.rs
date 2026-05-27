use numpy::PyArray2;
use pyo3::prelude::*;
use numpy::PyReadonlyArray1;

/// 计算分子指纹的两两 Tanimoto 相似度矩阵
///
/// Args:
///     fps: 分子指纹列表，每个指纹是 uint8 数组
///
/// Returns:
///     N x N 相似度矩阵，对角线为 1.0
///
/// # Example
///
/// ```python
/// import numpy as np
/// from mbforge_core import pairwise_tanimoto_matrix
///
/// fps = [np.array([1, 0, 1, 1, 0], dtype=np.uint8) for _ in range(100)]
/// matrix = pairwise_tanimoto_matrix(fps)
/// ```
#[pyfunction]
fn pairwise_tanimoto_matrix<'py>(
    py: Python<'py>,
    fps: Vec<PyReadonlyArray1<'py, u8>>,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let n = fps.len();
    if n == 0 {
        return PyArray2::<f64>::zeros(py, (0, 0), false);
    }

    let dim = fps[0].as_array().len();
    let mut matrix = vec![0.0f64; n * n];

    // 对角线设为 1.0
    for i in 0..n {
        matrix[i * n + i] = 1.0;
    }

    // 计算上三角（利用对称性）
    for i in 0..n {
        let a = fps[i].as_array();
        for j in (i + 1)..n {
            let b = fps[j].as_array();
            let mut intersection = 0u64;
            let mut union = 0u64;

            for k in 0..dim {
                let ai = a[k] != 0;
                let bi = b[k] != 0;
                if ai && bi {
                    intersection += 1;
                }
                if ai || bi {
                    union += 1;
                }
            }

            let sim = if union == 0 {
                0.0
            } else {
                intersection as f64 / union as f64
            };

            matrix[i * n + j] = sim;
            matrix[j * n + i] = sim;
        }
    }

    Ok(PyArray2::from_vec_bound(py, n, n, matrix))
}
