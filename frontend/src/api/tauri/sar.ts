/** SAR 分析 — Tauri 原生（替代 Python sidecar HTTP） */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError, ErrorCode } from './_utils'

export interface ScaffoldResult {
  scaffold_smarts: string
  atom_count: number
  bond_count: number
}

export interface RGroupEntry {
  position: number
  label: string
  substituent_smiles: string
  substituent_atoms: number
}

export interface RGroupDecomposition {
  compound_id: string
  compound_name: string
  smiles: string
  core_matches: boolean
  r_groups: RGroupEntry[]
}

export interface CompoundInput {
  id: string
  name: string
  smiles: string
  activity?: number
  activity_type?: string
  units?: string
}

export interface RGroupMatrix {
  core_smiles: string
  r_labels: string[]
  rows: string[][]
  compounds: Array<Record<string, unknown> & { id: string; name: string; smiles: string; matches: boolean }>
  unmatched_count: number
}

export interface HeatmapCell {
  substituent_smiles: string
  avg_activity: number
  count: number
  min: number
  max: number
}

export interface ActivityHeatmap {
  r_label: string
  cells: HeatmapCell[]
}

/** 提取共同骨架（MCS，带 ring constraints） */
export async function sarFindScaffold(smilesList: string[]): Promise<ScaffoldResult | null> {
  return invokeWithError(
    () => invoke<ScaffoldResult | null>('sar_find_scaffold', { smilesList }),
    ErrorCode.ApiError,
  )
}

/** 分解单个化合物为骨架 + R-group */
export async function sarDecompose(smiles: string, coreSmiles: string): Promise<RGroupDecomposition> {
  return invokeWithError(
    () => invoke<RGroupDecomposition>('sar_decompose', { smiles, coreSmiles }),
    ErrorCode.ApiError,
  )
}

/** 构建 R-group 矩阵 */
export async function sarBuildMatrix(
  compounds: CompoundInput[],
  coreSmiles?: string,
): Promise<RGroupMatrix> {
  return invokeWithError(
    () => invoke<RGroupMatrix>('sar_build_matrix', { compounds, coreSmiles: coreSmiles ?? null }),
    ErrorCode.ApiError,
  )
}

/** R-group 矩阵响应（含错误包装） */
export interface RGroupMatrixResponse {
  success: boolean
  core_smiles?: string
  r_labels?: string[]
  rows?: string[][]
  compounds?: RGroupMatrix['compounds']
  unmatched_count?: number
  error?: string
}

/** 活性热力图响应（含错误包装） */
export interface ActivityHeatmapResponse {
  success: boolean
  heatmaps: ActivityHeatmap[]
  error?: string
}

/** 兼容旧名 — client.ts 迁移 */
export type ActivityHeatmapEntry = ActivityHeatmap
export type ActivityHeatmapCell = HeatmapCell

/** 构建活性热力图 */
export async function sarHeatmap(
  matrix: RGroupMatrix,
  lowerIsBetter: boolean = true,
): Promise<ActivityHeatmap[]> {
  return invokeWithError(
    () => invoke<ActivityHeatmap[]>('sar_heatmap', { matrix, lowerIsBetter }),
    ErrorCode.ApiError,
  )
}
