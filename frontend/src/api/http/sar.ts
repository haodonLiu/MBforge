/** SAR 分析 — HTTP backend */

import { httpPost, invokeWithError, ErrorCode } from './_utils'

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

export interface CompoundMatch extends CompoundInput {
  matches: boolean
}

export interface RGroupMatrix {
  core_smiles: string
  r_labels: string[]
  rows: string[][]
  compounds: CompoundMatch[]
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
    () => httpPost<ScaffoldResult | null>('/api/v1/sar/find-scaffold', { smilesList }),
    ErrorCode.ApiError,
  )
}

/** 分解单个化合物为骨架 + R-group */
export async function sarDecompose(smiles: string, coreSmiles: string): Promise<RGroupDecomposition> {
  return invokeWithError(
    () => httpPost<RGroupDecomposition>('/api/v1/sar/decompose', { smiles, coreSmiles }),
    ErrorCode.ApiError,
  )
}

/** 构建 R-group 矩阵 */
export async function sarBuildMatrix(
  compounds: CompoundInput[],
  coreSmiles?: string,
): Promise<RGroupMatrix> {
  return invokeWithError(
    () => httpPost<RGroupMatrix>('/api/v1/sar/build-matrix', { compounds, coreSmiles: coreSmiles ?? null }),
    ErrorCode.ApiError,
  )
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
    () => httpPost<ActivityHeatmap[]>('/api/v1/sar/heatmap', { matrix, lowerIsBetter }),
    ErrorCode.ApiError,
  )
}
