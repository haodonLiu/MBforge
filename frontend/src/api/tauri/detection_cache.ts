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
  source: 'cache' | 'sidecar' | 'sidecar_error'
  cache_path?: string | null
  error?: string | null
}

export interface DetectionCacheStats {
  disk_usage_bytes: number
  cached_page_count: number
  cached_doc_count: number
  schema_version: number
}

/** Cache-aware single-page molecule detection. */
export async function cachedExtractPage(params: {
  projectRoot: string
  docSlug: string
  page: number
  imageBase64: string
  pageWPts: number
  pageHPts: number
  imageW: number
  imageH: number
}): Promise<CachedExtractPageResponse> {
  return invoke<CachedExtractPageResponse>('cached_extract_page', {
    projectRoot: params.projectRoot,
    docSlug: params.docSlug,
    page: params.page,
    imageBase64: params.imageBase64,
    pageWPts: params.pageWPts,
    pageHPts: params.pageHPts,
    imageW: params.imageW,
    imageH: params.imageH,
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
