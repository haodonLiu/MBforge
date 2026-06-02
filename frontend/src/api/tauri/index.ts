/** Tauri IPC barrel — re-exports from focused submodules.
 *
 * Layout:
 * - _utils:    shared utilities (isTauriAvailable)
 * - text:      text ops, page/document classifier, extractor
 * - pdf:       PDF classify, extract, parse, process_document
 * - agent:     agent session + post-process
 * - kb:        knowledge base (index, search, structure, pages)
 * - molecule:  molecule store + analysis wrappers
 * - project:   project open, scan, file ops
 * - environment: resource manager / env check
 *
 * Use specific submodules directly to keep bundle splitting clean;
 * importing this barrel pulls in everything.
 */

export * from './_utils'
export * from './text'
export * from './pdf'
export * from './agent'
export * from './kb'
export * from './molecule'
export * from './project'
export * from './environment'
