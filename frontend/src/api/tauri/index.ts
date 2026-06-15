/** Tauri IPC barrel — re-exports from focused submodules.
 *
 * Layout:
 * - _utils:    shared utilities (isTauriAvailable)
 * - text:      text ops, page/document classifier, extractor
 * - pdf:       PDF classify, extract, parse, process_document
 * - agent:     agent session
 * - kb:        knowledge base (index, search, structure, pages)
 * - molecule:  molecule store + analysis wrappers
 * - project:   project open, scan, file ops
 * - environment: resource manager / env check
 * - download:    model download / delete / list
 * - settings:    app settings + build info
 * - notes:       notes CRUD + backlinks
 * - audit:       audit log
 * - sar:         SAR analysis
 * - detection_cache: per-PDF detection cache
 * - ingest_queue:    PDF 处理队列
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
export * from './moleculeAdmin'
export * from './project'
export * from './environment'
export * from './sidecar'
export * from './download'
export * from './settings'
export * from './notes'
export * from './audit'
export * from './sar'
export * from './detection_cache'
export * from './ingest_queue'
