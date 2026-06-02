/** Text utilities — chunking, page classification, structured extraction. */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

// ---- text_ops ----

export interface TextChunkResult {
  chunks: string[]
  total_chunks: number
}

export async function textChunk(text: string, chunkSize = 512, overlap = 128): Promise<TextChunkResult> {
  return invokeWithError(
    () => invoke<TextChunkResult>('text_chunk', { text, chunkSize, overlap }),
    ErrorCode.ApiError,
  )
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
    () => invoke<PageClassification>('classify_page', { pageText, pageIdx }),
    ErrorCode.ApiError,
  )
}

export async function classifyDocument(pages: string[], metadata?: Record<string, unknown>): Promise<DocumentClassification> {
  return invokeWithError(
    () => invoke<DocumentClassification>('classify_document', { pages, metadata: metadata ?? null }),
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
  return invoke<string[]>('extract_smiles_candidates', { text })
}

export async function extractActivities(text: string): Promise<ActivityData[]> {
  return invoke<ActivityData[]>('extract_activities', { text })
}
