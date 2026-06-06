#!/usr/bin/env python3
"""Fix core/mod.rs re-exports by replacing shortened paths with full paths."""

import os
import re
from pathlib import Path

ROOT = Path("C:/Users/10954/Desktop/MBForge/src-tauri/src")
CORE_MOD = ROOT / "core/mod.rs"

# Map of old (re-exported) paths -> new (full) paths
REPLACEMENTS = {
    "crate::core::knowledge_base": "crate::core::document::knowledge_base",
    "crate::core::molecule_store": "crate::core::molecule::molecule_store",
    "crate::core::molecule_engine": "crate::core::molecule::molecule_engine",
    "crate::core::molecule_db": "crate::core::molecule::molecule_db",
    "crate::core::resource_manager": "crate::core::project::resource_manager",
    "crate::core::gesim": "crate::core::chem::gesim",
    "crate::core::esmiles": "crate::core::chem::esmiles",
    "crate::core::molecode": "crate::core::chem::molecode",
    "crate::core::abbreviation_map": "crate::core::chem::abbreviation_map",
    "crate::core::notes::": "crate::core::project::notes::",
}

# Re-export lines in core/mod.rs to remove (they are unused or problematic)
REEXPORT_LINES_TO_REMOVE = [
    # document re-exports
    "pub use document::document_tree;",
    "pub use document::document_tree::{DocumentTreeIndex, PageContent};",
    "pub use document::knowledge_base;",
    "pub use document::knowledge_base::{",
    "    get_or_init_kb, kb_get_pages, kb_get_structure, kb_search, kb_search_stream,",
    "    search_with_cache, KnowledgeBase,",
    "};",
    "pub use document::file_cache;",
    "pub use document::file_cache::{CacheStats, FileCache};",
    "pub use vector::sqlite_vector_store::{SqliteVectorStore, reciprocal_rank_fusion};",
    "pub use document::semantic_cache;",
    "pub use document::semantic_cache::{SemanticCache, SemanticCacheConfig};",
    "pub use document::stream_search;",
    "pub use document::stream_search::{StreamingResult, StreamingSearch, StreamingSearchConfig};",
    "pub use document::summary;",
    "pub use document::summary::SummaryManager;",
    # agent re-exports
    "pub use agent::context;",
    "pub use agent::observability;",
    "pub use agent::memory::MemoryManager;",
    "pub use agent::skills::SkillsManager;",
    "pub use agent::trajectory::TrajectoryTracker;",
    # molecule re-exports
    "pub use molecule::molecule_cluster;",
    "pub use molecule::molecule_cluster::ClusterInfo;",
    "pub use molecule::molecule_db;",
    "pub use molecule::molecule_db::{",
    "    MoleculeRelation, MoleculeRelationDb, RelationStats, RelationType, MOL_DB_FILENAME,",
    "};",
    "pub use molecule::molecule_dedup;",
    "pub use molecule::molecule_dedup::{",
    "    add_similarity_relation, run_dedup_batch, DedupPair, DedupResult,",
    "};",
    "pub use molecule::molecule_engine;",
    "pub use molecule::molecule_engine::{",
    "    ActivityCliff, ActivitySummary, AnalogWithActivity, MarkushOverlap, MarkushPattern,",
    "    MoleculeEngine, ScaffoldActivityRecord, ScaffoldProfile,",
    "};",
    "pub use molecule::molecule_store;",
    "pub use molecule::molecule_store::{MoleculeDatabase, MoleculeRecord};",
    # chem re-exports
    "pub use chem::abbreviation_map;",
    "pub use chem::chem as chem_functions;",
    "pub use chem::esmiles;",
    "pub use chem::gesim;",
    "pub use chem::markush;",
    "pub use chem::molecode;",
    # project re-exports
    "pub use project::notes;",
    "pub use project::resource_manager;",
    "pub use project::project as project_ops;",
    "pub use project::project::Project;",
    # vector re-exports
    "pub use vector::embedding;",
    "pub use vector::vector_store;",
]


def find_and_replace_in_files():
    """Replace all re-exported paths with full paths in .rs files."""
    changes = []
    for rs_file in ROOT.rglob("*.rs"):
        if rs_file.name == "mod.rs" and "core" in str(rs_file.parent):
            # Skip core/mod.rs itself - we handle it separately
            if rs_file == CORE_MOD:
                continue
        text = rs_file.read_text(encoding="utf-8")
        original = text
        for old_path, new_path in REPLACEMENTS.items():
            text = text.replace(old_path, new_path)
        if text != original:
            rs_file.write_text(text, encoding="utf-8")
            changes.append(str(rs_file.relative_to(ROOT)))
    return changes


def remove_reexports_from_core_mod():
    """Remove problematic re-export lines from core/mod.rs."""
    text = CORE_MOD.read_text(encoding="utf-8")
    original = text
    for line in REEXPORT_LINES_TO_REMOVE:
        text = text.replace(line + "\n", "")
        # Also try without trailing newline in case it's at end of file
        text = text.replace(line, "")
    # Clean up multiple consecutive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    if text != original:
        CORE_MOD.write_text(text, encoding="utf-8")
        return True
    return False


if __name__ == "__main__":
    print("Step 1: Replacing re-exported paths with full paths...")
    changed_files = find_and_replace_in_files()
    for f in changed_files:
        print(f"  -> {f}")
    print(f"Total files changed: {len(changed_files)}")

    print("\nStep 2: Removing re-exports from core/mod.rs...")
    if remove_reexports_from_core_mod():
        print("  -> core/mod.rs updated")
    else:
        print("  -> No changes needed in core/mod.rs")

    print("\nDone.")
