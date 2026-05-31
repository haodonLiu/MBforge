import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'

/** True when running inside a Tauri webview (desktop app). */
export function isTauriAvailable(): boolean {
  try {
    return typeof window !== 'undefined' && (
      typeof (window as any).__TAURI_INTERNALS__ !== 'undefined' ||
      typeof (window as any).__TAURI__ !== 'undefined'
    )
  } catch {
    return false
  }
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
  metadata: DocumentMetadata
  compounds: CompoundEntry[]
  activities: ActivityEntry[]
  key_findings: FindingEntry[]
  sar_analysis: string
  uncertain_items: UncertainItem[]
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

export interface CompoundEntry {
  name: string
  smiles: string | null
  category: string | null
  description: string
  source_ref: string
  confidence: string
  uncertainty_reason: string | null
}

export interface ActivityEntry {
  compound: string
  activity_type: string
  value: number
  units: string
  target: string | null
  source_quote: string
  source_ref: string
  confidence: string
  uncertainty_reason: string | null
}

export interface FindingEntry {
  finding: string
  evidence: string
  source_ref: string
  confidence: string
  uncertainty_reason: string | null
}

export interface UncertainItem {
  item_type: string
  content: string
  reason: string
  suggested_action: string
}

export interface DocumentMetadata {
  title: string | null
  authors: string[]
  document_type: string
  key_targets: string[]
  source_file: string | null
}

export interface StructuredData {
  metadata: DocumentMetadata
  summary: string
  compounds: CompoundEntry[]
  activities: ActivityEntry[]
  key_findings: FindingEntry[]
  uncertain_items: UncertainItem[]
}

export interface PostProcessResult {
  report: string
  data: StructuredData
  model: string
  tokens_used: number | null
  batch_count: number
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
  try {
    return await invoke<IndexResult>('index_project_rust', { root })
  } catch (e: unknown) {
    const msg = (e as Error)?.message || String(e) || 'Unknown error'
    // Tauri v2 on Windows sometimes has transient IPC protocol failures
    if (msg.includes('ipc.localhost') || msg.includes('ERR_CONNECTION_REFUSED') || msg.includes('Failed to fetch')) {
      console.warn('[tauri-bridge] IPC transport failure, retrying once...')
      await new Promise(r => setTimeout(r, 500))
      return invoke<IndexResult>('index_project_rust', { root })
    }
    throw e
  }
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

// ---- project_ops ----

export interface ProjectInfo {
  name: string
  root: string
  document_count: number
}

export interface ProjectResponse {
  success: boolean
  project?: ProjectInfo
  error?: string
}

/** 打开或创建项目（Rust native，不依赖 Python sidecar） */
export async function openProject(
  root: string,
  name?: string,
): Promise<ProjectResponse> {
  console.log('[tauri-bridge] === openProject START ===')
  console.log('[tauri-bridge] Root:', root)
  console.log('[tauri-bridge] Name:', name)

  try {
    console.log('[tauri-bridge] Calling invoke("open_project", {...})')
    const response = await invoke<ProjectResponse>('open_project', { 
      root, 
      name: name ?? null 
    })
    console.log('[tauri-bridge] Response:', JSON.stringify(response, null, 2))
    console.log('[tauri-bridge] === openProject END ===')
    return response
  } catch (e: unknown) {
    const error = e as Error
    console.error('[tauri-bridge] === openProject ERROR ===')
    console.error('[tauri-bridge] Error:', error?.message || String(e))
    const msg = error?.message || String(e) || 'Unknown invoke error'
    return { success: false, error: msg }
  }
}

/** 项目文档条目 */
export interface DocumentEntry {
  doc_id: string
  path: string
  doc_type: string
  title: string
  indexed: boolean
  added_at: string
  hash: string
}

/** 扫描项目文件 */
export async function scanProjectFiles(
  root: string,
): Promise<{ success: boolean; documents: DocumentEntry[] }> {
  return invoke('scan_project_files', { root })
}

/** 列出项目文档 */
export async function listProjectDocuments(
  root: string,
  docType?: string,
): Promise<{ success: boolean; documents: DocumentEntry[] }> {
  return invoke('list_project_documents', { root, docType: docType ?? null })
}

/** 文件树节点 */
export interface FileNode {
  name: string
  path: string
  is_dir: boolean
  children: FileNode[]
}

/** 获取项目文件树 */
export async function getFileTree(
  root: string,
): Promise<{ success: boolean; tree: FileNode[] }> {
  return invoke('get_file_tree', { root })
}

/** 使用系统对话框导入文件到项目 */
export async function uploadFiles(projectRoot: string): Promise<DocumentEntry[]> {
  return invoke<DocumentEntry[]>('upload_files', { projectRoot })
}

/** 删除项目中的文件 */
export async function deleteFile(projectRoot: string, docId: string): Promise<boolean> {
  return invoke<boolean>('delete_file', { projectRoot, docId })
}

/** 读取文本文件内容（Rust 直接读取，无需 HTTP） */
export async function readTextFile(path: string): Promise<string> {
  return invoke<string>('read_text_file', { path })
}

/** 列出项目文档（与 client.ts listDocuments 兼容的包装） */
export async function listDocumentsTauri(
  root: string,
): Promise<{ success: boolean; documents: DocumentEntry[]; error?: string }> {
  try {
    const resp = await listProjectDocuments(root)
    return { success: true, documents: resp.documents }
  } catch (e) {
    return { success: false, documents: [], error: String(e) }
  }
}

/** 分子统计（与 client.ts moleculeStats 兼容的包装） */
export async function moleculeStatsTauri(
  projectRoot: string,
): Promise<{ success: boolean; stats: Record<string, unknown>; error?: string }> {
  try {
    const stats = await molStoreStats(projectRoot)
    return { success: true, stats: stats as unknown as Record<string, unknown> }
  } catch (e) {
    return { success: false, stats: {}, error: String(e) }
  }
}

/** 列出分子（与 client.ts listMolecules 兼容的包装） */
export async function listMoleculesTauri(
  projectRoot: string,
  limit = 100,
  offset = 0,
): Promise<{ success: boolean; molecules: import('../types').MoleculeRecord[]; error?: string }> {
  try {
    const records = await molStoreList(projectRoot, limit, offset)
    const molecules = records.map((r) => ({
      mol_id: r.mol_id,
      esmiles: r.esmiles,
      name: r.name,
      source_doc: r.source_doc,
      source_type: r.source_type,
      activity: r.activity,
      activity_type: r.activity_type,
      units: r.units,
      status: r.status,
      properties: r.properties,
      tags: r.tags,
      notes: r.notes,
      created_at: r.created_at,
    }))
    return { success: true, molecules }
  } catch (e) {
    return { success: false, molecules: [], error: String(e) }
  }
}

/** 搜索分子（与 client.ts searchMolecules 兼容的包装） */
export async function searchMoleculesTauri(
  projectRoot: string,
  q: string,
): Promise<{ success: boolean; molecules: import('../types').MoleculeRecord[]; error?: string }> {
  try {
    const records = await molStoreSearch(projectRoot, q)
    const molecules = records.map((r) => ({
      mol_id: r.mol_id,
      esmiles: r.esmiles,
      name: r.name,
      source_doc: r.source_doc,
      source_type: r.source_type,
      activity: r.activity,
      activity_type: r.activity_type,
      units: r.units,
      status: r.status,
      properties: r.properties,
      tags: r.tags,
      notes: r.notes,
      created_at: r.created_at,
    }))
    return { success: true, molecules }
  } catch (e) {
    return { success: false, molecules: [], error: String(e) }
  }
}

// ---- molecule_store ----

export interface MoleculeRecord {
  mol_id: string
  esmiles: string
  name: string
  source_doc: string
  source_type: string
  activity: number | null
  activity_type: string
  units: string
  status: string
  properties: Record<string, unknown>
  tags: string[]
  notes: string
  created_at: string
}

export interface MolStoreStats {
  total: number
  with_activity: number
  pending: number
}

export async function molStoreInit(projectRoot: string): Promise<void> {
  return invoke<void>('mol_store_init', { projectRoot })
}

export async function molStoreAdd(
  projectRoot: string,
  molId: string,
  esmiles: string,
  name?: string,
  sourceDoc?: string,
  activity?: number,
  activityType?: string,
  units?: string,
  sourceType?: string,
): Promise<void> {
  return invoke<void>('mol_store_add', {
    projectRoot,
    molId,
    esmiles,
    name: name ?? null,
    sourceDoc: sourceDoc ?? null,
    activity: activity ?? null,
    activityType: activityType ?? null,
    units: units ?? null,
    sourceType: sourceType ?? null,
  })
}

export async function molStoreList(
  projectRoot: string,
  limit?: number,
  offset?: number,
  sourceType?: string,
  status?: string,
): Promise<MoleculeRecord[]> {
  return invoke<MoleculeRecord[]>('mol_store_list', {
    projectRoot,
    limit: limit ?? null,
    offset: offset ?? null,
    sourceType: sourceType ?? null,
    status: status ?? null,
  })
}

export async function molStoreGet(
  projectRoot: string,
  molId: string,
): Promise<MoleculeRecord | null> {
  return invoke<MoleculeRecord | null>('mol_store_get', { projectRoot, molId })
}

export async function molStoreSearch(
  projectRoot: string,
  query: string,
): Promise<MoleculeRecord[]> {
  return invoke<MoleculeRecord[]>('mol_store_search', { projectRoot, query })
}

export async function molStoreDelete(
  projectRoot: string,
  molId: string,
): Promise<boolean> {
  return invoke<boolean>('mol_store_delete', { projectRoot, molId })
}

export async function molStoreStats(
  projectRoot: string,
): Promise<MolStoreStats> {
  return invoke<MolStoreStats>('mol_store_stats', { projectRoot })
}

export async function molStoreSearchBySmiles(
  projectRoot: string,
  esmiles: string,
): Promise<MoleculeRecord | null> {
  return invoke<MoleculeRecord | null>('mol_store_search_by_smiles', { projectRoot, esmiles })
}

export async function molStoreListByDoc(
  projectRoot: string,
  docId: string,
): Promise<MoleculeRecord[]> {
  return invoke<MoleculeRecord[]>('mol_store_list_by_doc', { projectRoot, docId })
}
