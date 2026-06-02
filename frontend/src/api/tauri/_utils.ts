/** Shared utilities for Tauri IPC bridges. */

/** True when running inside a Tauri webview (desktop app). */
export function isTauriAvailable(): boolean {
  try {
    return typeof window !== 'undefined' && (
      typeof (window as any).__TAURI_INTERNALS__ !== 'undefined' ||
      typeof (window as any).__TAURI__ !== 'undefined'
    )
  } catch {
    return false
  }
}
