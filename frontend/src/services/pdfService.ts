/**
 * PDF 服务层 — 前端到后端的统一接口
 *
 * 分层架构：
 *   UI 组件 → pdfService (本文件) → HTTP → Python Backend
 *
 * 设计原则：
 *   1. 所有 HTTP 调用封装在此，UI 层不直接 import httpPost
 *   2. 错误统一处理，返回 { success, data?, error? }
 *   3. 支持取消和超时
 */

import { httpPost } from '../api/http/_utils'
import type {
  ExtractionResult,
} from '../types'

// ============================================================================
// 通用类型
// ============================================================================

export interface ServiceResult<T> {
  success: boolean
  data?: T
  error?: string
}

export interface DetectionResponse {
  results: ExtractionResult[]
  count: number
  source: 'cache' | 'sidecar' | 'sidecar_error' | 'cache_miss'
  cachePath?: string
}

function normalizeDetection(raw: Record<string, unknown>, page: number, index: number): ExtractionResult {
  const rawBbox = raw.bbox_pdf ?? raw.bbox
  const bbox = Array.isArray(rawBbox)
    ? rawBbox.map(Number) as [number, number, number, number]
    : rawBbox && typeof rawBbox === 'object'
      ? [
        Number((rawBbox as Record<string, unknown>).x1),
        Number((rawBbox as Record<string, unknown>).y1),
        Number((rawBbox as Record<string, unknown>).x2),
        Number((rawBbox as Record<string, unknown>).y2),
      ] as [number, number, number, number]
      : null
  const confidence = Number(raw.composite_conf ?? raw.confidence ?? raw.moldet_conf ?? 0)
  const esmiles = typeof raw.esmiles === 'string'
    ? raw.esmiles
    : typeof raw.smiles === 'string' ? raw.smiles : ''
  const name = typeof raw.name === 'string'
    ? raw.name
    : `Mol_${String(index + 1).padStart(3, '0')}`
  const contextText = typeof raw.context_text === 'string' ? raw.context_text : ''

  return {
    esmiles,
    smiles: esmiles,
    name,
    source: 'image',
    moldet_conf: confidence,
    scribe_conf: Number(raw.scribe_conf ?? confidence),
    composite_conf: confidence,
    bbox_pdf: bbox,
    page_idx: Number.isFinite(Number(raw.page_idx)) ? Number(raw.page_idx) : page - 1,
    context_text: contextText,
    mol_img_path: typeof raw.mol_img_path === 'string' ? raw.mol_img_path : null,
    status: 'pending',
    properties: raw.properties && typeof raw.properties === 'object'
      ? raw.properties as Record<string, unknown>
      : {},
  }
}

export interface CacheStats {
  diskUsageBytes: number
  cachedPageCount: number
  cachedDocCount: number
  schemaVersion: number
}

export interface PageParseResult {
  page: number
  structuredText: Array<{
    kind: string
    content: string
    bbox: [number, number, number, number]
  }>
  molecules: ExtractionResult[]
  findings: Array<{
    kind: string
    text: string
    bbox: [number, number, number, number]
  }>
}

export interface CorefChain {
  molId: string
  occurrences: Array<{
    docId: string
    page: number
    bbox: [number, number, number, number]
    context: string
    confidence: number
    smiles: string
    esmiles: string
  }>
  aliases: string[]
}

// ============================================================================
// 分子检测 API
// ============================================================================

export async function detectPageMolecules(params: {
  libraryRoot: string
  docId: string
  page: number
  imageBase64: string
  pageWPts: number
  pageHPts: number
  imageW: number
  imageH: number
  force?: boolean
}): Promise<ServiceResult<DetectionResponse>> {
  // 2026-07-08: migrated from /api/v1/models/extract/cached-page (legacy
  // stub returning 503) to the new FT-based main pipeline endpoint.
  // No server-side cache: every call runs FT detector + MolScribe.
  // The `force` parameter is kept for API compatibility but ignored.
  try {
    const resp = await httpPost<{
      molecules: ExtractionResult[]
      count: number
      page_num: number
      width: number
      height: number
    }>('/api/v1/moldet/extract-pdf', {
      library_root: params.libraryRoot,
      doc_id: params.docId,
      page: params.page,
      dpi: 300,
      use_coref: false,
    })
    return {
      success: true,
      data: {
        results: resp.molecules.map((raw, index) => normalizeDetection(raw as Record<string, unknown>, params.page, index)),
        count: resp.count,
        source: 'sidecar',
      },
    }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

export async function getCachedDetections(params: {
  libraryRoot: string
  docId: string
  page: number
}): Promise<ServiceResult<DetectionResponse>> {
  try {
    const resp = await httpPost<{
      results: unknown[]
      count: number
      source: string
    }>('/api/v1/models/extract/cached-detections', {
      library_root: params.libraryRoot,
      doc_id: params.docId,
      page: params.page,
    })

    return {
      success: true,
      data: {
        results: resp.results as ExtractionResult[],
        count: resp.count,
        source: resp.source as DetectionResponse['source'],
      },
    }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

export async function clearDocumentDetections(
  libraryRoot: string,
  docId: string,
): Promise<ServiceResult<void>> {
  try {
    await httpPost('/api/v1/models/extract/clear-cache-doc', { library_root: libraryRoot, doc_id: docId })
    return { success: true }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

export async function getDetectionStats(
  libraryRoot: string,
): Promise<ServiceResult<CacheStats>> {
  try {
    const resp = await httpPost<{
      disk_usage_bytes: number
      cached_page_count: number
      cached_doc_count: number
      schema_version: number
    }>('/api/v1/models/extract/cache-stats', { library_root: libraryRoot })

    return {
      success: true,
      data: {
        diskUsageBytes: resp.disk_usage_bytes,
        cachedPageCount: resp.cached_page_count,
        cachedDocCount: resp.cached_doc_count,
        schemaVersion: resp.schema_version,
      },
    }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

// ============================================================================
// 页面解析 API
// ============================================================================

export async function getPageParseResult(params: {
  libraryRoot: string
  docId: string
  page: number
  pageHPts: number
}): Promise<ServiceResult<PageParseResult>> {
  try {
    const resp = await httpPost<{
      page: number
      structured_text: Array<{ kind: string; content: string; bbox: [number, number, number, number] }>
      molecules: unknown[]
      findings: Array<{ kind: string; text: string; bbox: [number, number, number, number] }>
    }>('/api/v1/models/parse/page', {
      library_root: params.libraryRoot,
      doc_id: params.docId,
      page: params.page,
      page_h_pts: params.pageHPts,
    })

    return {
      success: true,
      data: {
        page: resp.page,
        structuredText: resp.structured_text,
        molecules: resp.molecules as ExtractionResult[],
        findings: resp.findings,
      },
    }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

// ============================================================================
// Coref 链 API
// ============================================================================

export async function getMoleculeCorefChain(
  libraryRoot: string,
  molId: string,
): Promise<ServiceResult<CorefChain>> {
  try {
    const resp = await httpPost<{
      mol_id: string
      occurrences: Array<{
        doc_id: string
        page: number
        bbox: [number, number, number, number]
        context: string
        confidence: number
        smiles: string
        esmiles: string
      }>
      aliases: string[]
    }>('/api/v1/models/coref/chain', { library_root: libraryRoot, mol_id: molId })

    return {
      success: true,
      data: {
        molId: resp.mol_id,
        occurrences: resp.occurrences.map(o => ({
          docId: o.doc_id,
          page: o.page,
          bbox: o.bbox,
          context: o.context,
          confidence: o.confidence,
          smiles: o.smiles,
          esmiles: o.esmiles,
        })),
        aliases: resp.aliases,
      },
    }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

// ============================================================================
// OCR 布局 API
// ============================================================================

export interface OcrBlock {
  page: number
  blockType: string
  bbox: [number, number, number, number]
  content: string | null
  index: number
  angle: number
}

export interface OcrLayoutResult {
  path: string
  parser: string
  pageCount: number
  blocks: OcrBlock[]
  fromCache: boolean
}

export async function getOcrLayout(
  path: string,
  docId?: string,
): Promise<ServiceResult<OcrLayoutResult>> {
  try {
    const resp = await httpPost<{
      path: string
      parser: string
      page_count: number
      blocks: Array<{
        page: number
        block_type: string
        bbox: [number, number, number, number]
        content: string | null
        index: number
        angle: number
      }>
      from_cache: boolean
    }>('/api/v1/models/ocr/layout', { path, doc_id: docId })

    return {
      success: true,
      data: {
        path: resp.path,
        parser: resp.parser,
        pageCount: resp.page_count,
        blocks: resp.blocks.map(b => ({
          page: b.page,
          blockType: b.block_type,
          bbox: b.bbox,
          content: b.content,
          index: b.index,
          angle: b.angle,
        })),
        fromCache: resp.from_cache,
      },
    }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

// ============================================================================
// PDF 分类 API
// ============================================================================

export interface PdfClassification {
  pdfType: string
  confidence: number
  pageCount: number
  pagesNeedingOcr: number[]
  textDensityAvg: number
  hasComplexLayout: boolean
  hasEncodingIssues: boolean
  title: string | null
}

export async function classifyPdf(
  path: string,
): Promise<ServiceResult<PdfClassification>> {
  try {
    const resp = await httpPost<{
      pdf_type: string
      confidence: number
      page_count: number
      pages_needing_ocr: number[]
      text_density_avg: number
      has_complex_layout: boolean
      has_encoding_issues: boolean
      title: string | null
    }>('/api/v1/models/pdf/classify', { path })

    return {
      success: true,
      data: {
        pdfType: resp.pdf_type,
        confidence: resp.confidence,
        pageCount: resp.page_count,
        pagesNeedingOcr: resp.pages_needing_ocr,
        textDensityAvg: resp.text_density_avg,
        hasComplexLayout: resp.has_complex_layout,
        hasEncodingIssues: resp.has_encoding_issues,
        title: resp.title,
      },
    }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

// ============================================================================
// Sidecar 状态 API
// ============================================================================

export interface SidecarHealth {
  healthy: boolean
  restartCount: number
  state: 'online' | 'offline'
  uptimeSecs: number
  lastError: string | null
}

export async function getSidecarStatus(): Promise<ServiceResult<SidecarHealth>> {
  try {
    const resp = await httpPost<{
      healthy: boolean
      restart_count: number
      state: string
      uptime_secs: number
      last_error: string | null
    }>('/api/v1/sidecar/status')

    return {
      success: true,
      data: {
        healthy: resp.healthy,
        restartCount: resp.restart_count,
        state: resp.state as SidecarHealth['state'],
        uptimeSecs: resp.uptime_secs,
        lastError: resp.last_error,
      },
    }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

export async function restartSidecar(): Promise<ServiceResult<void>> {
  try {
    await httpPost('/api/v1/sidecar/restart')
    return { success: true }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

// ============================================================================
// 批量扫描 API
// ============================================================================

export interface QuickScanResult {
  docId: string
  pageCount: number
  pagesWithMolecules: number[]
  moldetStatus: string
}

export async function batchQuickScan(
  libraryRoot: string,
  docIds?: string[],
): Promise<ServiceResult<QuickScanResult[]>> {
  try {
    const resp = await httpPost<{
      results: Array<{
        doc_id: string
        page_count: number
        pages_with_molecules: number[]
        moldet_status: string
      }>
      processed: number
      total: number
      errors: string[]
    }>('/api/v1/models/moldet/batch-scan', {
      library_root: libraryRoot,
      doc_ids: docIds ?? [],
    })

    return {
      success: true,
      data: resp.results.map(r => ({
        docId: r.doc_id,
        pageCount: r.page_count,
        pagesWithMolecules: r.pages_with_molecules,
        moldetStatus: r.moldet_status,
      })),
    }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

// ============================================================================
// PDF 图片提取 API
// ============================================================================

export interface ImageRef {
  filename: string
  page: number
  region: string | null
  description: string | null
  esmiles: string | null
  rel_path: string | null
}

export async function extractPdfImages(
  path: string,
  chunkSize?: number,
  overlap?: number,
  parser?: string,
): Promise<ServiceResult<ImageRef[]>> {
  try {
    const resp = await httpPost<{
      images: Array<{
        filename: string
        page: number
        region: string | null
        description: string | null
        esmiles: string | null
        rel_path: string | null
      }>
    }>('/api/v1/models/pdf/parse', {
      path,
      chunk_size: chunkSize ?? 512,
      overlap: overlap ?? 128,
      parser: parser ?? 'pdf_inspector',
    })

    return {
      success: true,
      data: resp.images.map(img => ({
        filename: img.filename,
        page: img.page,
        region: img.region,
        description: img.description,
        esmiles: img.esmiles,
        rel_path: img.rel_path,
      })),
    }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}
