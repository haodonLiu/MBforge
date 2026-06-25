//! Build script for mbforge-infra.
//!
//! Runs `scripts/generate_constants.py` to produce YAML-derived Rust constants
//! into `OUT_DIR/constants.rs`, which `src/config/generated.rs` pulls in via
//! `include!`.
//!
//! Python discovery: prefer `uv run python` (project-standard toolchain) so
//! PyYAML is guaranteed; fall back to plain `python`/`python3` for users who
//! have installed dev deps some other way.
//!
//! If the script fails, `cargo build` fails — drift is caught at compile time.
//! Rust-only constants (Tauri event names, path helpers, project layout) live
//! in `src/config/constants.rs` and are NOT touched here.

use std::path::PathBuf;
use std::process::Command;

fn main() {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest_dir
        .parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.parent())
        .expect("mbforge-infra should be at src-tauri/crates/mbforge-infra");

    let script = repo_root.join("scripts").join("generate_constants.py");
    let yaml = repo_root.join("constants.yaml");
    let out_dir = PathBuf::from(
        std::env::var("OUT_DIR").expect("cargo must set OUT_DIR for build scripts"),
    );

    println!("cargo:rerun-if-changed={}", script.display());
    println!("cargo:rerun-if-changed={}", yaml.display());

    let mut cmd = if Command::new("uv").arg("--version").output().is_ok() {
        let mut c = Command::new("uv");
        c.args(["run", "--no-sync", "python"]);
        c
    } else {
        Command::new("python")
    };
    cmd.arg(&script).arg("--rust-out").arg(&out_dir);

    let status = cmd.status().unwrap_or_else(|e| {
        panic!(
            "failed to spawn python/uv: {e}. \
             Install Python 3.11+ with PyYAML, or `uv` from astral-sh."
        )
    });

    if !status.success() {
        panic!(
            "constants codegen failed (exit {:?}). \
             Check constants.yaml and scripts/generate_constants.py.",
            status.code()
        );
    }
}
