/**
 * PDF 服务层 — 前端到后端的统一接口
 *
 * 分层架构：
 *   UI 组件 → pdfService (本文件) → Tauri IPC → Rust 命令 → Python Sidecar
 *
 * 设计原则：
 *   1. 所有 Tauri invoke 调用封装在此，UI 层不直接 import invoke
 *   2. 错误统一处理，返回 { success, data?, error? }
 *   3. 支持取消和超时
 */

import { invoke } from '@tauri-apps/api/core'
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

/**
 * 缓存感知的单页分子检测
 */
export async function detectPageMolecules(params: {
  projectRoot: string
  docId: string
  page: number
  imageBase64: string
  pageWPts: number
  pageHPts: number
  imageW: number
  imageH: number
  force?: boolean
}): Promise<ServiceResult<DetectionResponse>> {
  try {
    const resp = await invoke<{
      results: unknown[]
      count: number
      source: string
      cache_path?: string
      error?: string
    }>('cached_extract_page', {
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

    if (resp.source === 'sidecar_error') {
      return { success: false, error: resp.error || '检测失败' }
    }

    return {
      success: true,
      data: {
        results: resp.results as ExtractionResult[],
        count: resp.count,
        source: resp.source as DetectionResponse['source'],
        cachePath: resp.cache_path ?? undefined,
      },
    }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

/**
 * 仅读取缓存的检测结果
 */
export async function getCachedDetections(params: {
  projectRoot: string
  docId: string
  page: number
}): Promise<ServiceResult<DetectionResponse>> {
  try {
    const resp = await invoke<{
      results: unknown[]
      count: number
      source: string
    }>('get_cached_page_detections', {
      projectRoot: params.projectRoot,
      docId: params.docId,
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

/**
 * 清除单文档检测缓存
 */
export async function clearDocumentDetections(
  projectRoot: string,
  docId: string,
): Promise<ServiceResult<void>> {
  try {
    await invoke('clear_detection_cache_doc', { projectRoot, docId })
    return { success: true }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

/**
 * 获取检测缓存统计
 */
export async function getDetectionStats(
  projectRoot: string,
): Promise<ServiceResult<CacheStats>> {
  try {
    const resp = await invoke<{
      disk_usage_bytes: number
      cached_page_count: number
      cached_doc_count: number
      schema_version: number
    }>('get_detection_cache_stats', { projectRoot })

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

/**
 * 获取页面解析结果（结构化文本 + 分子 + 发现）
 */
export async function getPageParseResult(params: {
  projectRoot: string
  docId: string
  page: number
  pageHPts: number
}): Promise<ServiceResult<PageParseResult>> {
  try {
    const resp = await invoke<{
      page: number
      structured_text: Array<{ kind: string; content: string; bbox: [number, number, number, number] }>
      molecules: unknown[]
      findings: Array<{ kind: string; text: string; bbox: [number, number, number, number] }>
    }>('get_page_parse_result', {
      projectRoot: params.projectRoot,
      docId: params.docId,
      page: params.page,
      pageHPts: params.pageHPts,
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

/**
 * 获取分子的跨页 coref 链
 */
export async function getMoleculeCorefChain(
  projectRoot: string,
  molId: string,
): Promise<ServiceResult<CorefChain>> {
  try {
    const resp = await invoke<{
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
    }>('get_molecule_coref_chain', { projectRoot, molId })

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

/**
 * 获取文档 OCR 布局
 */
export async function getOcrLayout(
  path: string,
  docId?: string,
): Promise<ServiceResult<OcrLayoutResult>> {
  try {
    const resp = await invoke<{
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
    }>('get_document_ocr_layout', { path, doc_id: docId })

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

/**
 * 快速分类 PDF 类型
 */
export async function classifyPdf(
  path: string,
): Promise<ServiceResult<PdfClassification>> {
  try {
    const resp = await invoke<{
      pdf_type: string
      confidence: number
      page_count: number
      pages_needing_ocr: number[]
      text_density_avg: number
      has_complex_layout: boolean
      has_encoding_issues: boolean
      title: string | null
    }>('classify_pdf', { path })

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

/**
 * 获取 sidecar 状态
 */
export async function getSidecarStatus(): Promise<ServiceResult<SidecarHealth>> {
  try {
    const resp = await invoke<{
      healthy: boolean
      restart_count: number
      state: string
      uptime_secs: number
      last_error: string | null
    }>('sidecar_status')

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

/**
 * 重启 sidecar
 */
export async function restartSidecar(): Promise<ServiceResult<void>> {
  try {
    await invoke('sidecar_restart')
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

/**
 * 批量快速 MoldDet 扫描
 */
export async function batchQuickScan(
  projectRoot: string,
  docIds?: string[],
): Promise<ServiceResult<QuickScanResult[]>> {
  try {
    const resp = await invoke<{
      results: Array<{
        doc_id: string
        page_count: number
        pages_with_molecules: number[]
        moldet_status: string
      }>
      processed: number
      total: number
      errors: string[]
    }>('batch_quick_moldet_scan', {
      request: { project_root: projectRoot, doc_ids: docIds ?? [] },
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

/**
 * 提取 PDF 中的图片
 */
export async function extractPdfImages(
  path: string,
  chunkSize?: number,
  overlap?: number,
  parser?: string,
): Promise<ServiceResult<ImageRef[]>> {
  try {
    const resp = await invoke<{
      images: Array<{
        filename: string
        page: number
        region: string | null
        description: string | null
        esmiles: string | null
        rel_path: string | null
      }>
    }>('parse_pdf', {
      path,
      chunkSize: chunkSize ?? 512,
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
