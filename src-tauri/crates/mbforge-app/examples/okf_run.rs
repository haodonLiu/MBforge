//! Standalone runner for the OKF pipeline command.
//!
//! Usage:
//!   cargo run -p mbforge-app --example okf_run -- \
//!     --pdf <path> --text-dir <dir> --project <dir> [--manifest <path>]
//!
//! Reads per-page text from text-dir, calls LLM, joins, writes OKF bundle.

use std::path::PathBuf;

#[tokio::main]
async fn main() -> Result<(), String> {
    let _ = simple_logger();
    let args: Vec<String> = std::env::args().collect();
    let mut pdf = String::new();
    let mut text_dir = String::new();
    let mut project = String::new();
    let mut manifest = String::new();
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--pdf" => { pdf = args[i + 1].clone(); i += 2; }
            "--text-dir" => { text_dir = args[i + 1].clone(); i += 2; }
            "--project" => { project = args[i + 1].clone(); i += 2; }
            "--manifest" => { manifest = args[i + 1].clone(); i += 2; }
            _ => { i += 1; }
        }
    }
    if pdf.is_empty() || text_dir.is_empty() || project.is_empty() {
        eprintln!(
            "usage: okf_run --pdf <pdf> --text-dir <dir> --project <dir> [--manifest <path>]\n\
             env: MOFORGE_LLM_BASE_URL MOFORGE_LLM_API_KEY"
        );
        std::process::exit(2);
    }
    let manifest = if manifest.is_empty() {
        PathBuf::from(&project).join("manifest.json").to_string_lossy().to_string()
    } else {
        manifest
    };
    let result = mbforge_app::commands::okf_pipeline::okf_extract_patent_cmd(
        pdf, text_dir, manifest, project,
    )
    .await?;
    println!("{}", serde_json::to_string_pretty(&result).unwrap_or_default());
    Ok(())
}

fn simple_logger() -> Result<(), String> {
    let _ = simple_logger_no_op();
    Ok(())
}

fn simple_logger_no_op() -> std::io::Result<()> {
    Ok(())
}
