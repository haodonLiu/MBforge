const API_BASE = '/api/v1'

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`HTTP ${resp.status}: ${text}`)
  }
  return resp.json() as Promise<T>
}

// Health
export function getHealth() {
  return fetchJson<import('../types').HealthResponse>(`${API_BASE}/health`)
}

// LLM
export function chat(messages: { role: string; content: string }[], temperature = 0.7, maxTokens = 4096) {
  return fetchJson<{ content: string }>(`${API_BASE}/llm/chat`, {
    method: 'POST',
    body: JSON.stringify({ messages, temperature, max_tokens: maxTokens }),
  })
}

export function chatStream(messages: { role: string; content: string }[], temperature = 0.7, maxTokens = 4096) {
  return new EventSource(
    `${API_BASE}/llm/chat-stream?` +
    new URLSearchParams({
      messages: JSON.stringify(messages),
      temperature: String(temperature),
      max_tokens: String(maxTokens),
    }),
  )
}

// Embed
export function embed(texts: string[]) {
  return fetchJson<{ embeddings: number[][] }>(`${API_BASE}/embed`, {
    method: 'POST',
    body: JSON.stringify({ texts }),
  })
}

// Rerank
export function rerank(query: string, passages: string[], topN = 5) {
  return fetchJson<{ results: { index: number; score: number }[] }>(`${API_BASE}/rerank`, {
    method: 'POST',
    body: JSON.stringify({ query, passages, top_n: topN }),
  })
}

// VLM
export function describeImage(imageBase64: string, prompt = '') {
  return fetchJson<{ description: string }>(`${API_BASE}/vlm/describe`, {
    method: 'POST',
    body: JSON.stringify({ image_base64: imageBase64, prompt }),
  })
}

// MolDet
export function detectPage(imageBase64: string) {
  return fetchJson<{ boxes: { x1: number; y1: number; x2: number; y2: number; conf: number }[]; count: number }>(
    `${API_BASE}/moldet/detect-page`,
    { method: 'POST', body: JSON.stringify({ image_base64: imageBase64 }) },
  )
}

export function extractPage(imageBase64: string, pageIdx: number, pageWPts: number, pageHPts: number, imageW: number, imageH: number, dpi = 300) {
  return fetchJson<{ results: Record<string, unknown>[]; count: number }>(
    `${API_BASE}/moldet/extract-page`,
    {
      method: 'POST',
      body: JSON.stringify({ image_base64: imageBase64, page_idx: pageIdx, page_w_pts: pageWPts, page_h_pts: pageHPts, image_w: imageW, image_h: imageH, dpi }),
    },
  )
}

// UniParser
export function parsePdf(pdfPath: string = '', pdfBase64: string = '') {
  return fetchJson<{ status: string; token: string; raw_data: Record<string, unknown> }>(
    `${API_BASE}/uniparser/parse`,
    { method: 'POST', body: JSON.stringify({ pdf_path: pdfPath, pdf_base64: pdfBase64 }) },
  )
}

// Project
export function createProject(root: string, name: string = '') {
  return fetchJson<{ success: boolean; project: import('../types').Project; error?: string }>(
    `${API_BASE}/project/create`,
    { method: 'POST', body: JSON.stringify({ root, name }) },
  )
}

export function openProject(root: string, name: string = '') {
  return fetchJson<{ success: boolean; project: import('../types').Project; error?: string }>(
    `${API_BASE}/project/open`,
    { method: 'POST', body: JSON.stringify({ root, name }) },
  )
}

export function listDocuments(projectRoot: string) {
  return fetchJson<{ success: boolean; documents: import('../types').DocumentEntry[]; error?: string }>(
    `${API_BASE}/project/list?root=${encodeURIComponent(projectRoot)}`,
  )
}

export function scanProject(projectRoot: string) {
  return fetchJson<{ success: boolean; documents: import('../types').DocumentEntry[]; error?: string }>(
    `${API_BASE}/project/scan`,
    { method: 'POST', body: JSON.stringify({ root: projectRoot }) },
  )
}

export function indexProject(root: string) {
  return fetchJson<{ success: boolean; indexed: number; molecules: number; error?: string }>(
    `${API_BASE}/project/index`,
    { method: 'POST', body: JSON.stringify({ root }) },
  )
}

// Knowledge Base
export function kbSearch(projectRoot: string, query: string, topK = 5) {
  return fetchJson<{ success: boolean; results: import('../types').SearchResult[]; error?: string }>(
    `${API_BASE}/kb/search`,
    { method: 'POST', body: JSON.stringify({ project_root: projectRoot, query, top_k: topK }) },
  )
}

export function kbStats(projectRoot: string) {
  return fetchJson<{ success: boolean; stats: Record<string, unknown>; error?: string }>(
    `${API_BASE}/kb/stats?project_root=${encodeURIComponent(projectRoot)}`,
  )
}

// Molecule
export function listMolecules(projectRoot: string, limit = 100, offset = 0) {
  return fetchJson<{ success: boolean; molecules: import('../types').MoleculeRecord[]; error?: string }>(
    `${API_BASE}/molecule/list?project_root=${encodeURIComponent(projectRoot)}&limit=${limit}&offset=${offset}`,
  )
}

export function moleculeStats(projectRoot: string) {
  return fetchJson<{ success: boolean; stats: Record<string, unknown>; error?: string }>(
    `${API_BASE}/molecule/stats?project_root=${encodeURIComponent(projectRoot)}`,
  )
}

export function searchMolecules(projectRoot: string, q: string, limit = 20) {
  return fetchJson<{ success: boolean; molecules: import('../types').MoleculeRecord[]; error?: string }>(
    `${API_BASE}/molecule/search?project_root=${encodeURIComponent(projectRoot)}&q=${encodeURIComponent(q)}&limit=${limit}`,
  )
}

export function addMolecule(projectRoot: string, smiles: string, name = '', sourceDoc = '', activity?: number) {
  return fetchJson<{ success: boolean; mol_id?: string; error?: string }>(
    `${API_BASE}/molecule/add`,
    { method: 'POST', body: JSON.stringify({ project_root: projectRoot, smiles, name, source_doc: sourceDoc, activity }) },
  )
}

// Agent
export function agentChat(projectRoot: string, messages: { role: string; content: string }[], temperature = 0.7) {
  return fetchJson<{ success: boolean; content: string; error?: string }>(
    `${API_BASE}/agent/chat`,
    { method: 'POST', body: JSON.stringify({ project_root: projectRoot, messages, temperature }) },
  )
}

export function agentChatStream(projectRoot: string, messages: { role: string; content: string }[], temperature = 0.7) {
  return new EventSource(
    `${API_BASE}/agent/chat-stream?` +
    new URLSearchParams({
      messages: JSON.stringify(messages),
      project_root: projectRoot,
      temperature: String(temperature),
    }),
  )
}

// File
export function uploadFile(projectRoot: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  form.append('project_root', projectRoot)
  return fetchJson<{ success: boolean; doc_id?: string; path?: string; doc_type?: string; error?: string }>(
    `${API_BASE}/file/upload`,
    { method: 'POST', body: form },
  )
}

export function deleteFile(projectRoot: string, docId: string) {
  return fetchJson<{ success: boolean; error?: string }>(
    `${API_BASE}/file/delete`,
    { method: 'POST', body: JSON.stringify({ project_root: projectRoot, doc_id: docId }) },
  )
}

// File Tree
export function getFileTree(projectRoot: string) {
  return fetchJson<{ success: boolean; tree: import('../types').FileNode[]; error?: string }>(
    `${API_BASE}/project/file-tree?root=${encodeURIComponent(projectRoot)}`,
  )
}
