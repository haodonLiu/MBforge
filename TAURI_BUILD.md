# Tauri Desktop Build

## Prerequisites

1. **Rust** (https://rustup.rs/)
2. **Node.js** (already have for frontend)

## Setup

```bash
# Install Tauri CLI
cargo install tauri-cli

# Generate icons (optional)
cargo tauri icon path/to/logo.png
```

## Development

```bash
# Start frontend dev server + Tauri window
cd frontend && npm run dev
# In another terminal:
cargo tauri dev
```

Or use the combined command:
```bash
cargo tauri dev
```

## Production Build

```bash
# Build frontend first
cd frontend && npm run build

# Build Tauri app
cargo tauri build
```

Output:
- Windows: `src-tauri/target/release/bundle/msi/*.msi`
- macOS: `src-tauri/target/release/bundle/dmg/*.dmg`
- Linux: `src-tauri/target/release/bundle/deb/*.deb`

## Architecture

```
Tauri Window (WebView)
  -> Loads frontend/dist (React app)
  -> Frontend calls FastAPI backend via HTTP (127.0.0.1:18792)
  -> Tauri spawns Python backend on startup
```

## Notes

- Backend runs as separate Python process, started by Tauri
- Frontend communicates via HTTP (same as browser mode)
- For distribution, Python + dependencies must be bundled (e.g. PyInstaller)
