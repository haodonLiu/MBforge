/** Tauri commands wrapping the per-PDF detection cache.
 *
 * - `cachedExtractPage` — cache-aware single-page molecule detection.
 *   Returns the same shape as the Python sidecar's
 *   `/api/v1/moldet/extract-page`, with an extra `source` field
 *   (`"cache"` | `"sidecar"` | `"sidecar_error"`).
 * - `getDetectionCacheStats` — disk usage + page count for Settings.
 * - `clearDetectionCache` — wipe all `index/detections` JSON files.
 */

import { invoke } from '@tauri-apps/api/core'

export interface CachedExtractPageResponse {
  results: unknown[]
  count: number
  source: 'cache' | 'sidecar' | 'sidecar_error' | 'cache_miss'
  cache_path?: string | null
  error?: string | null
}

export interface DetectionCacheStats {
  disk_usage_bytes: number
  cached_page_count: number
  cached_doc_count: number
  schema_version: number
}

/** Cache-aware single-page molecule detection.
 *
 * `docId` is the document UUID (`DocumentEntry.doc_id`). The backend resolves
 * the actual PDF source path from the project index.
 */
export async function cachedExtractPage(params: {
  projectRoot: string
  docId: string
  page: number
  imageBase64: string
  pageWPts: number
  pageHPts: number
  imageW: number
  imageH: number
  force?: boolean
}): Promise<CachedExtractPageResponse> {
  return invoke<CachedExtractPageResponse>('cached_extract_page', {
    projectRoot: params.projectRoot,
    docId: params.docId,
    page: params.page,
    imageBase64: params.imageBase64,
    pageWPts: params.pageWPts,
    pageHPts: params.pageHPts,
    imageW: params.imageW,
    imageH: params.imageH,
    force: params.force ?? false,
  })
}

/** Read cached detections for a page without calling the sidecar.
 *  Used by the PDF viewer to render bbox overlays instantly when a quick scan
 *  has already populated the cache.
 *
 * `docId` is the document UUID (`DocumentEntry.doc_id`).
 */
export async function getCachedPageDetections(params: {
  projectRoot: string
  docId: string
  page: number
}): Promise<CachedExtractPageResponse> {
  return invoke<CachedExtractPageResponse>('get_cached_page_detections', {
    projectRoot: params.projectRoot,
    docId: params.docId,
    page: params.page,
  })
}

export async function getDetectionCacheStats(
  projectRoot: string,
): Promise<DetectionCacheStats> {
  return invoke<DetectionCacheStats>('get_detection_cache_stats', { projectRoot })
}

export async function clearDetectionCache(projectRoot: string): Promise<void> {
  return invoke<void>('clear_detection_cache', { projectRoot })
}

export async function clearDetectionCacheForDoc(
  projectRoot: string,
  docId: string,
): Promise<void> {
  return invoke<void>('clear_detection_cache_doc', { projectRoot, docId })
}

// ---------------------------------------------------------------------------
// 批量快速 MoldDet 扫描
// ---------------------------------------------------------------------------

export interface QuickMoldetPageResult {
  page: number
  has_molecule: boolean
  bbox_count: number
}

export interface QuickMoldetDocResult {
  path: string
  doc_slug: string
  doc_id: string
  page_count: number
  pages: QuickMoldetPageResult[]
  pages_with_molecules: number[]
  moldet_status: string
  error?: string | null
}

export interface BatchQuickMoldetResponse {
  results: QuickMoldetDocResult[]
  processed: number
  total: number
  errors: string[]
}

/** 批量快速 MoldDet 扫描：只检测 bbox，不识别 SMILES。 */
export async function batchQuickMoldetScan(
  projectRoot: string,
  docIds?: string[],
): Promise<BatchQuickMoldetResponse> {
  return invoke<BatchQuickMoldetResponse>('batch_quick_moldet_scan', {
    request: { project_root: projectRoot, doc_ids: docIds ?? [] },
  })
}
