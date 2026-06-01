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

// ---- SAR 分析 ----

/** 单个分子实体（用于 SAR 表）*/
export interface SARCompound {
  id: string
  /** E-SMILES */
  smiles: string
  /** 化合物名称 / 编号 */
  name: string
  /** R-group 取代基位置（以原子索引为 key）*/
  rGroups: Record<number, string>
  /** 活性数据 */
  activity?: number
  /** 活性类型（IC50 / EC50 / Ki ...）*/
  activityType?: string
  /** 单位（nM / uM ...）*/
  units?: string
  /** 选择性数据 */
  selectivity?: Record<string, number>
  /** 备注 */
  notes?: string
}

/** SAR 分析会话 */
export interface SARSession {
  id: string
  /** 课题名称 */
  name: string
  /** 靶点 / 蛋白 */
  target?: string
  /** 化合物列表 */
  compounds: SARCompound[]
  /** 核心骨架 SMILES（用于 R-group 分析）*/
  coreSmiles?: string
  /** 关联的文献 */
  sourceDocs?: string[]
  /** 创建时间 */
  createdAt: string
}
