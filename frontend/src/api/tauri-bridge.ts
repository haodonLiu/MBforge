import { invoke } from '@tauri-apps/api/core'

/** True when running inside a Tauri webview (desktop app). */
export function isTauriAvailable(): boolean {
  return typeof window !== 'undefined' && '__TAURI__' in window
}

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

// ---- text_ops ----

export interface TextChunkResult {
  chunks: string[]
  total_chunks: number
}

export async function textChunk(text: string, chunkSize = 512, overlap = 128): Promise<TextChunkResult> {
  return invoke<TextChunkResult>('text_chunk', { text, chunkSize, overlap })
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
  return invoke<PageClassification>('classify_page', { pageText, pageIdx })
}

export async function classifyDocument(pages: string[], metadata?: Record<string, unknown>): Promise<DocumentClassification> {
  return invoke<DocumentClassification>('classify_document', { pages, metadata: metadata ?? null })
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

// ---- pipeline ----

export interface PdfParseResult {
  content: string
  classification: DocumentClassification
  chunks: string[]
  smiles: string[]
  activities: ActivityData[]
  parser: string
  page_count: number
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

// ---- agent ----

export interface ChatMessage {
  role: string
  content: string
}

export async function agentInit(projectRoot: string): Promise<void> {
  await invoke('agent_init', { projectRoot })
}

export async function agentChat(
  projectRoot: string,
  messages: ChatMessage[],
): Promise<string> {
  return invoke<string>('agent_chat', { projectRoot, messages })
}

export async function agentClear(projectRoot: string): Promise<void> {
  await invoke('agent_clear', { projectRoot })
}

export async function agentGetHistory(projectRoot: string): Promise<ChatMessage[]> {
  return invoke<ChatMessage[]>('agent_get_history', { projectRoot })
}

// ---- post_process ----

export interface ActivityRecord {
  compound: string
  activity_type: string
  value: number
  units: string
  target: string | null
  context: string
}

export interface DocumentMetadata {
  title: string | null
  authors: string[]
  document_type: string
  key_compounds: string[]
  key_targets: string[]
}

export interface PostProcessResult {
  summary: string
  structured_content: string
  validated_smiles: string[]
  activity_records: ActivityRecord[]
  key_findings: string[]
  metadata: DocumentMetadata
  model: string
  tokens_used: number | null
}

export async function postProcessPdf(parseResult: PdfParseResult): Promise<PostProcessResult> {
  return invoke<PostProcessResult>('post_process_pdf', { parseResult })
}
