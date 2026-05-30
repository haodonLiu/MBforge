fn main() {
    // 自动设置 PDFium 路径（如果 vendor 目录存在）
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_default();
    let vendor_lib = std::path::PathBuf::from(&manifest_dir)
        .join("vendor/pdfium/release/lib");
    let vendor_include = std::path::PathBuf::from(&manifest_dir)
        .join("vendor/pdfium/release/include");

    if vendor_lib.exists() && vendor_include.exists() {
        if std::env::var("PDFIUM_LIB_PATH").is_err() {
            println!("cargo:rustc-env=PDFIUM_LIB_PATH={}", vendor_lib.display());
        }
        if std::env::var("PDFIUM_INCLUDE_PATH").is_err() {
            println!("cargo:rustc-env=PDFIUM_INCLUDE_PATH={}", vendor_include.display());
        }
    }

    tauri_build::build()
}
