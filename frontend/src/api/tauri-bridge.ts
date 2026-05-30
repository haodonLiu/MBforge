import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'

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
  heading: string
  text: string
  page: number
  section_id: string
}

export interface PdfParseResult {
  content: string
  classification: DocumentClassification
  chunks: string[]
  smiles: string[]
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

// ---- agent (session-based, per-conversation isolation) ----

export interface ChatMessage {
  role: string
  content: string
}

export async function agentInit(config: {
  provider: string
  base_url: string
  api_key: string
  model_name: string
  max_tokens: number
  temperature: number
  top_p: number
}, sidecarUrl: string): Promise<void> {
  await invoke('agent_init', { config, sidecarUrl })
}

export async function agentCreateSession(sessionId: string, projectRoot?: string): Promise<void> {
  await invoke('agent_create_session', { sessionId, projectRoot: projectRoot ?? null })
}

export async function agentChat(sessionId: string, userInput: string): Promise<string> {
  return invoke<string>('agent_chat', { sessionId, userInput })
}

export type AgentStreamEvent = {
  session_id: string
  delta: string
  finish_reason: string | null
}

export interface DocumentReport {
  metadata: { title: string | null; authors: string[]; document_type: string; key_targets: string[]; source_file: string | null }
  compounds: { name: string; smiles: string | null; category: string | null; description: string; source_ref: string; confidence: string; uncertainty_reason: string | null }[]
  activities: { compound: string; activity_type: string; value: number; units: string; target: string; source_quote: string; source_ref: string; confidence: string }[]
  key_findings: { finding: string; evidence: string; source_ref: string; confidence: string }[]
  sar_analysis: string
  uncertain_items: { item_type: string; content: string; reason: string; suggested_action: string }[]
  report_markdown: string
}

export async function agentChatStream(
  sessionId: string,
  userInput: string,
  onChunk: (delta: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): Promise<() => void> {
  // Start streaming
  invoke('agent_chat_stream', { sessionId, userInput }).catch(err => onError(String(err)))

  // Listen for chunks
  const unlistenChunk = await listen<AgentStreamEvent>('agent-stream-chunk', (event) => {
    if (event.payload.session_id === sessionId) {
      onChunk(event.payload.delta)
      if (event.payload.finish_reason) {
        onDone()
      }
    }
  })

  // Listen for done signal
  const unlistenDone = await listen<{ session_id: string }>('agent-stream-done', (event) => {
    if (event.payload.session_id === sessionId) {
      onDone()
    }
  })

  return () => {
    unlistenChunk()
    unlistenDone()
  }
}

export async function agentSwitchProject(sessionId: string, projectRoot: string, projectName: string): Promise<void> {
  await invoke('agent_switch_project', { sessionId, projectRoot, projectName })
}

export async function agentClear(sessionId: string): Promise<void> {
  await invoke('agent_clear', { sessionId })
}

export async function agentDestroySession(sessionId: string): Promise<void> {
  await invoke('agent_destroy_session', { sessionId })
}

export async function agentGetHistory(sessionId: string): Promise<ChatMessage[]> {
  return invoke<ChatMessage[]>('agent_get_history', { sessionId })
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

// ---- process_document (A3: 完整文档处理管线) ----

export interface DocProgressEvent {
  stage: string
  payload: Record<string, unknown>
}

export async function processDocument(
  path: string,
  userRequest?: string,
): Promise<void> {
  return invoke<void>('process_document', {
    path,
    userRequest: userRequest ?? '',
  })
}

// ---- knowledge_base ----

export interface IndexResult {
  indexed: number
  sections: number
  errors: string[]
}

export async function indexProjectRust(root: string): Promise<IndexResult> {
  return invoke<IndexResult>('index_project_rust', { root })
}

export interface KbSearchResult {
  id: string
  text: string
  metadata: Record<string, unknown>
  score: number
}

export async function kbSearch(
  projectRoot: string,
  query: string,
  topK = 5,
): Promise<KbSearchResult[]> {
  return invoke<KbSearchResult[]>('kb_search', { projectRoot, query, topK })
}

export interface TreeNode {
  title: string
  node_id: string
  line_num: number
  nodes: TreeNode[]
}

export async function kbGetStructure(
  projectRoot: string,
  docId: string,
): Promise<TreeNode[] | null> {
  return invoke<TreeNode[] | null>('kb_get_structure', { projectRoot, docId })
}

export interface PageContent {
  page: number
  content: string
}

export async function kbGetPages(
  projectRoot: string,
  docId: string,
  pages: string,
): Promise<PageContent[]> {
  return invoke<PageContent[]>('kb_get_pages', { projectRoot, docId, pages })
}
