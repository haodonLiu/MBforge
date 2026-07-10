/** 模型元数据（来自 /api/v1/models/list） */
export interface ModelInfo {
  id: string
  name: string
  type: string
  description: string
  downloaded: boolean
  downloading: boolean
  size_mb: number
  actual_size_mb: number
  license: string
  location: {
    found: boolean
    locations: ModelLocation[]
    primary: string | null
  }
}

export interface ModelLocation {
  path: string
  source: 'huggingface' | 'modelscope' | 'local'
}

export interface ModelPaths {
  mbforge: { path: string; exists: boolean; size_mb: number }
  huggingface: { path: string; env_var: string; exists: boolean; size_mb: number }
  modelscope: { path: string; env_var: string; exists: boolean; size_mb: number }
}
