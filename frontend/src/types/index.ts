export interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface Project {
  name: string
  root: string
  document_count: number
  molecule_count: number
  indexed_count: number
}

export interface DocumentEntry {
  doc_id: string
  path: string
  doc_type: string
  title: string
  indexed: boolean
}

export interface SearchResult {
  id: string
  text: string
  metadata: Record<string, unknown>
  distance: number
}

export interface MoleculeRecord {
  mol_id: string
  smiles: string
  esmiles?: string
  name: string
  source_doc: string
  activity: number | null
  activity_type: string
  units: string
  properties: Record<string, unknown>
}

export interface ModelStatus {
  status: 'ready' | 'loading' | 'error' | 'offline'
}

export interface HealthResponse {
  status: string
  models: Record<string, string>
  error: string | null
}

export interface FileNode {
  name: string
  path: string
  is_dir: boolean
  children: FileNode[]
}

export interface ChatMessage {
  id?: string
  role: string
  content: string
  timestamp?: string
}

// ---- MolDet 分子检测结果 ----

/** MolDet 检测结果（与后端 ExtractionResult 对齐） */
export interface ExtractionResult {
  esmiles: string
  name: string
  source: 'image' | 'text' | 'manual'
  moldet_conf: number
  scribe_conf: number
  composite_conf: number
  bbox_pdf: [number, number, number, number] | null  // [x1, y1, x2, y2] PDF points
  page_idx: number | null
  context_text: string
  mol_img_path: string | null
  status: 'pending' | 'confirmed' | 'rejected'
  properties: Record<string, unknown>
}

/** MolDet 检测框（像素坐标） */
export interface DetectionBox {
  x1: number
  y1: number
  x2: number
  y2: number
  conf: number
  result?: ExtractionResult
}
