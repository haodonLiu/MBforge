/** PDF processing — classify, extract, parse, full pipeline. */

import { invoke } from '@tauri-apps/api/core'
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
  return invoke<PdfClassification>('classify_pdf', { path })
}

export async function extractText(path: string): Promise<PdfExtraction> {
  return invoke<PdfExtraction>('extract_text', { path })
}

// ---- pipeline ----

export interface ImageRef {
  filename: string
  page: number
  region: string | null
  description: string | null
  esmiles: string | null
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
  return invoke<PdfParseResult>('parse_pdf', {
    path,
    chunkSize: chunkSize ?? 512,
    overlap: overlap ?? 128,
    parser: parser ?? 'pdf_inspector',
  })
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
  return invoke<void>('process_document', {
    path,
    userRequest: userRequest ?? '',
    projectRoot,
  })
}
