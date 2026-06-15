use std::env;
use std::path::PathBuf;

fn main() {
    // 把项目根 pdfium/ 路径写入构建时 env（供运行时 libloading 解析 dll 用）。
    // 编译期链接由 src-tauri/.cargo/config.toml 的 [env] 段负责——
    // build.rs 的 cargo:rustc-env 只对 rustc 生效，传不到下游 build script。
    if let Ok(manifest) = env::var("CARGO_MANIFEST_DIR") {
        let pdfium_dir = PathBuf::from(manifest).parent().unwrap().join("pdfium");
        if pdfium_dir.exists() {
            println!(
                "cargo:rustc-env=PDFIUM_LIB_DIR={}",
                pdfium_dir.join("lib").display()
            );
        }
    }

    tauri_build::build()
}
