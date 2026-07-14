/**
 * Project→Library compat shim (minimal).
 *
 * After project→library migration, only two helpers remain in use:
 * - `getCommonDirs` — FolderPicker shortcuts (empty on web)
 * - `readTextFile`  — MarkdownViewer local/dev fetch
 *
 * Prefer `library.ts` for all new code.
 */

export function getCommonDirs(): { name: string; path: string }[] {
  // No OS folder enumeration in web mode; FolderPicker falls back to manual entry.
  return []
}

export async function readTextFile(
  _libraryRoot: string,
  path: string,
): Promise<string> {
  // Legacy project file-tree read is gone. Paths under the dev server public
  // root can still be fetched; absolute library artifact paths need library
  // document routes (not implemented here).
  const url = path.startsWith('/') || path.startsWith('http') ? path : `/${path}`
  const r = await fetch(url)
  if (!r.ok) throw new Error(`readTextFile ${path}: HTTP ${r.status}`)
  return await r.text()
}
