//! Service for persisting extracted pipeline molecules to the molecule store.

use std::path::Path;

use crate::core::molecule::molecule_store::MoleculeDatabase;
use crate::parsers::doc_types::StructuredData;
use crate::parsers::pipeline::error::{PersistError, PipelineError};
use crate::parsers::pipeline::services::helpers::{
    activity_entry_to_record, compound_entry_to_record,
};

/// Writes extracted compound and activity entries to the project's molecule database.
pub struct MoleculeStoreWriter;

impl MoleculeStoreWriter {
    /// Creates a new writer instance.
    pub fn new() -> Self {
        Self
    }

    /// Persists compounds and activities from `data` into the molecule store.
    ///
    /// Returns the number of records written.
    pub fn write(
        &self,
        project_root: &Path,
        data: &StructuredData,
        source_type: &str,
    ) -> Result<usize, PipelineError> {
        let source_doc = data.metadata.source_file.as_deref().unwrap_or("");
        let mut records = Vec::new();
        let mut skipped = 0usize;

        for compound in &data.compounds {
            match compound_entry_to_record(compound, source_doc, source_type) {
                Some(rec) => records.push(rec),
                None => skipped += 1,
            }
        }
        log::debug!(
            "[MoleculeStoreWriter] skipped {} compounds without valid records",
            skipped
        );

        for activity in &data.activities {
            records.push(activity_entry_to_record(activity, source_doc, source_type));
        }

        if records.is_empty() {
            return Ok(0);
        }

        let db = MoleculeDatabase::open(project_root)
            .map_err(|e| PipelineError::Persist(PersistError::MoleculeStoreFailed { detail: e }))?;

        db.add_molecules_batch(&records)
            .map_err(|e| PipelineError::Persist(PersistError::MoleculeStoreFailed { detail: e }))
    }
}
