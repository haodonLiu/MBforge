/** PDF processing — classify, extract, parse, full pipeline. */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'
import type { ActivityData, DocumentClassification } from './text'

// ---- pdf-inspector ----

export interface PdfClassification {
  pdf_type: string
  confidence: number
  page_count: number
  pages_needing_ocr: number[]
  text_density_avg: number
  has_complex_layout: boolean
  has_encoding_issues: boolean
  title: string | null
}

export interface PdfExtraction {
  markdown: string
  page_count: number
  pages_needing_ocr: number[]
  confidence: number
  has_complex_layout: boolean
  has_encoding_issues: boolean
}

export async function classifyPdf(path: string): Promise<PdfClassification> {
  return invokeWithError(
    () => invoke<PdfClassification>('classify_pdf', { path }),
    ErrorCode.PdfParse,
  )
}

export async function inspectPdf(
  projectRoot: string,
  docId: string,
): Promise<PdfClassification> {
  return invokeWithError(
    () => invoke<PdfClassification>('inspect_pdf', { projectRoot, docId }),
    ErrorCode.PdfParse,
  )
}

export async function confirmOcr(
  projectRoot: string,
  docId: string,
  confirm: boolean,
): Promise<{ success: boolean; doc_id: string; ocr_status: string; task_id: string }> {
  return invokeWithError(
    () => invoke<{ success: boolean; doc_id: string; ocr_status: string; task_id: string }>('confirm_ocr', {
      projectRoot,
      docId,
      confirm,
    }),
    ErrorCode.PdfParse,
  )
}

export async function extractText(path: string): Promise<PdfExtraction> {
  return invokeWithError(
    () => invoke<PdfExtraction>('extract_text', { path }),
    ErrorCode.PdfParse,
  )
}

// ---- pipeline ----

export interface ImageRef {
  filename: string
  page: number
  region: string | null
  description: string | null
  esmiles: string | null
  rel_path: string | null
}

export interface Heading {
  level: number
  title: string
  line_num: number
}

export interface SectionChunk {
  title: string
  path: string
  text: string
  page_start: number | null
  page_end: number | null
  line_start: number
  line_end: number
}

export interface PdfParseResult {
  content: string
  classification: DocumentClassification
  chunks: string[]
  esmiles: string[]
  activities: ActivityData[]
  parser: string
  page_count: number
  images: ImageRef[]
  headings: Heading[]
  sections: SectionChunk[]
  page_texts: string[]
}

export async function parsePdf(
  path: string,
  chunkSize?: number,
  overlap?: number,
  parser?: string,
): Promise<PdfParseResult> {
  return invokeWithError(
    () => invoke<PdfParseResult>('parse_pdf', {
      path,
      chunkSize: chunkSize ?? 512,
      overlap: overlap ?? 128,
      parser: parser ?? 'pdf_inspector',
    }),
    ErrorCode.PdfParse,
  )
}

// ---- process_document (A3: 完整文档处理管线) ----

export interface DocProgressEvent {
  stage: string
  payload: Record<string, unknown>
}

export async function processDocument(
  path: string,
  userRequest?: string,
  projectRoot?: string,
): Promise<void> {
  return invokeWithError(
    () => invoke('process_document', {
      path,
      userRequest: userRequest ?? '',
      projectRoot,
    }),
    ErrorCode.PdfParse,
  )
}

// ---- OCR 布局可视化 ----

export interface OcrBlock {
  page: number
  block_type: string
  bbox: [number, number, number, number]
  content: string | null
  index: number
  angle: number
}

export interface OcrLayoutResult {
  path: string
  parser: string
  page_count: number
  blocks: OcrBlock[]
  from_cache: boolean
}

export async function getDocumentOcrLayout(path: string, doc_id?: string): Promise<OcrLayoutResult> {
  return invokeWithError(
    () => invoke<OcrLayoutResult>('get_document_ocr_layout', { path, doc_id }),
    ErrorCode.PdfParse,
  )
}

// ---- 嵌入图在 PDF 页面上的 bbox（coref 投影用） ----

export interface FigureBbox {
  xref: number
  /** [x1, y1, x2, y2] in PDF points (bottom-left origin) */
  bbox_pdf: [number, number, number, number]
  width: number | null
  height: number | null
}

export interface PageFigureBboxes {
  page_num: number
  figures: FigureBbox[]
}

/** 返回整本 PDF 中所有嵌入图在各自页面上的 bbox。
 *
 * 用于 coref overlay 把 figure 局部 0-1 坐标投影到 PDF 页面坐标。
 */
export async function getFigureBboxes(pdfPath: string): Promise<PageFigureBboxes[]> {
  return invokeWithError(
    () => invoke<PageFigureBboxes[]>('get_figure_bboxes', { pdfPath }),
    ErrorCode.PdfParse,
  )
}
