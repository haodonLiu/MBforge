/** Text utilities — chunking, page classification, structured extraction. */

import { httpPost, invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

// ---- text_ops ----

export interface TextChunkResult {
  chunks: string[]
  total_chunks: number
}

export async function textChunk(text: string, chunkSize = 512, overlap = 128): Promise<TextChunkResult> {
  return invokeWithError(
    () => httpPost<TextChunkResult>('/api/v1/text/chunk', { text, chunkSize, overlap }),
    ErrorCode.ApiError,
  )
}

// ---- ocr test (cloud backend auth probe) ----

export interface OcrTestResult {
  ok: boolean
  status: number | null
  message: string
}

export async function testOcrMineru(host: string | null, apiKey: string): Promise<OcrTestResult> {
  return httpPost<OcrTestResult>('/api/v1/ocr/test-mineru', { host, apiKey })
}

export async function testOcrUniparser(host: string | null, apiKey: string): Promise<OcrTestResult> {
  return httpPost<OcrTestResult>('/api/v1/ocr/test-uniparser', { host, apiKey })
}

export async function testOcrPaddleocr(
  host: string | null,
  apiKey: string,
  model: string | null,
): Promise<OcrTestResult> {
  return httpPost<OcrTestResult>('/api/v1/ocr/test-paddleocr', { host, apiKey, model })
}

// ---- classifier ----

export interface PageClassification {
  page_idx: number
  text_density: number
  is_scanned: boolean
  has_molecular_patterns: boolean
}

export interface DocumentClassification {
  text_density: number
  is_scanned: boolean
  has_molecular_patterns: boolean
  metadata_hints: Record<string, unknown> | null
  pages: PageClassification[]
  needs_confirmation: boolean
}

export async function classifyPage(pageText: string, pageIdx: number): Promise<PageClassification> {
  return invokeWithError(
    () => httpPost<PageClassification>('/api/v1/classify/page', { pageText, pageIdx }),
    ErrorCode.ApiError,
  )
}

export async function classifyDocument(pages: string[], metadata?: Record<string, unknown>): Promise<DocumentClassification> {
  return invokeWithError(
    () => httpPost<DocumentClassification>('/api/v1/classify/document', { pages, metadata: metadata ?? null }),
    ErrorCode.ApiError,
  )
}

// ---- extractor ----

export interface ActivityData {
  activity_type: string
  value: number
  units: string
  context: string
}

export async function extractSmilesCandidates(text: string): Promise<string[]> {
  return httpPost<string[]>('/api/v1/extract/esmiles-candidates', { text })
}

export async function extractActivities(text: string): Promise<ActivityData[]> {
  return httpPost<ActivityData[]>('/api/v1/extract/activities', { text })
}

export interface AssociatedMolecule {
  esmiles: string
  activity: ActivityData | null
  position: number
  confidence: string
  source_doc: string
}

/** Extract e-smiles + nearby activity (200-char window) for association UI. */
export async function extractAssociatedMolecules(
  text: string,
  sourceDoc: string,
): Promise<AssociatedMolecule[]> {
  return httpPost<AssociatedMolecule[]>('/api/v1/extract/associated-molecules', {
    text,
    sourceDoc,
  })
}
