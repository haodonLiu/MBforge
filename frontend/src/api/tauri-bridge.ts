/** Backward-compatible barrel for legacy imports.
 *
 * The IPC bridge has been split into focused submodules under `./tauri/`.
 * Existing imports of `'./api/tauri-bridge'` continue to work via this
 * thin re-export layer. New code should import from specific submodules
 * (`./tauri/agent`, `./tauri/kb`, etc.) for better tree-shaking.
 */

export * from './tauri'
