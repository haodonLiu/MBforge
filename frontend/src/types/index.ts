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
