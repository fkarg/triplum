use pyo3::exceptions::PyKeyError;
use pyo3::prelude::*;
use pyo3_arrow::PySchema;

/// Canonical Arrow schema by table name. `dims` is required for `chunk_embeddings`.
#[pyfunction]
#[pyo3(signature = (name, dims=None))]
fn schema(name: &str, dims: Option<i32>) -> PyResult<PySchema> {
    triplum_core::schema::by_name(name, dims)
        .map(PySchema::new)
        .ok_or_else(|| PyKeyError::new_err(format!("unknown schema: {name}")))
}

#[pyfunction]
fn ts_max() -> i64 {
    triplum_core::time::TS_MAX
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(schema, m)?)?;
    m.add_function(wrap_pyfunction!(ts_max, m)?)?;
    Ok(())
}
