/** Molecule store + analysis wrappers (compatible with client.ts). */

import { httpPost, httpPut, httpDelete, invokeWithError } from './_utils'
import { ErrorCode } from '@/utils/errors'
import type { MoleculeRecord } from '@/types'
import {
  molAdminStoreStats,
  molAdminList,
  molAdminSearchText,
} from './molecule_admin'

export interface MoleculeRecord_ {
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
  await invokeWithError(
    () => httpPost('/api/v1/molecule/stats', { project_root: projectRoot }),
    ErrorCode.MoleculeSearch,
  )
}

/** @deprecated Use molAdminAdd from ./molecule_admin instead */
export async function molStoreAdd(
  projectRoot: string,
  molId: string,
  esmiles: string,
  name?: string,
  _sourceDoc?: string,
  _activity?: number,
  _activityType?: string,
  _units?: string,
  sourceType?: string,
): Promise<void> {
  await invokeWithError(
    () => httpPost('/api/v1/molecule/create', {
      project_root: projectRoot,
      mol_id: molId,
      smiles: esmiles,
      esmiles,
      name: name ?? '',
      source_type: sourceType ?? 'manual',
    }),
    ErrorCode.ApiError,
  )
}

/** @deprecated Use molAdminList from ./molecule_admin instead */
export async function molStoreList(
  projectRoot: string,
  limit?: number,
  offset?: number,
  _sourceType?: string,
  status?: string,
): Promise<MoleculeRecord_[]> {
  const page = offset != null && limit != null ? Math.floor(offset / limit) + 1 : 1
  const pageSize = limit ?? 50
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; items: MoleculeRecord_[]; total: number }>(
      '/api/v1/molecule/list',
      {
        project_root: projectRoot,
        page,
        page_size: pageSize,
        status: status ?? '',
      },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.items
}

/** @deprecated Use molAdminGet from ./molecule_admin instead */
export async function molStoreGet(
  projectRoot: string,
  molId: string,
): Promise<MoleculeRecord_ | null> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; molecule?: MoleculeRecord_ }>(
      '/api/v1/molecule/get',
      { project_root: projectRoot, mol_id: molId },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.success && resp.molecule ? resp.molecule : null
}

/** @deprecated Use molAdminSearchText from ./molecule_admin instead */
export async function molStoreSearch(
  projectRoot: string,
  query: string,
): Promise<MoleculeRecord_[]> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; results: MoleculeRecord_[] }>(
      '/api/v1/molecule/search',
      { project_root: projectRoot, query },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.results
}

/** @deprecated Use molAdminDelete from ./molecule_admin instead */
export async function molStoreDelete(
  projectRoot: string,
  molId: string,
): Promise<boolean> {
  const resp = await invokeWithError(
    () => httpDelete<{ success: boolean }>(
      `/api/v1/molecule/${molId}`,
      { project_root: projectRoot },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.success
}

/** @deprecated Use molAdminStoreStats from ./molecule_admin instead */
export async function molStoreStats(
  projectRoot: string,
): Promise<MolStoreStats> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; total: number; by_status: Record<string, number> }>(
      '/api/v1/molecule/stats',
      { project_root: projectRoot },
    ),
    ErrorCode.MoleculeSearch,
  )
  return {
    total: resp.total,
    with_activity: resp.total - resp.by_status.pending,
    pending: resp.by_status.pending,
  }
}

/** @deprecated Use molAdminSearchBySmiles from ./molecule_admin instead */
export async function molStoreSearchBySmiles(
  projectRoot: string,
  esmiles: string,
): Promise<MoleculeRecord_ | null> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; results: MoleculeRecord_[] }>(
      '/api/v1/molecule/search',
      { project_root: projectRoot, query: esmiles },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.results[0] ?? null
}

export async function molStoreListByDoc(
  projectRoot: string,
  docId: string,
): Promise<MoleculeRecord_[]> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; items: MoleculeRecord_[] }>(
      '/api/v1/molecule/list',
      { project_root: projectRoot, page: 1, page_size: 1000, status: '' },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.items.filter((m) => m.source_doc === docId)
}

/** @deprecated Use molAdminUpdate from ./molecule_admin instead */
export async function molStoreUpdate(
  projectRoot: string,
  record: MoleculeRecord_,
): Promise<boolean> {
  const resp = await invokeWithError(
    () => httpPut<{ success: boolean }>(
      `/api/v1/molecule/${record.mol_id}`,
      { project_root: projectRoot, ...record },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.success
}

export async function molStoreUpdateBatch(
  projectRoot: string,
  records: MoleculeRecord_[],
): Promise<{ updated: number; failed: string[] }> {
  let updated = 0
  const failed: string[] = []
  for (const record of records) {
    try {
      await httpPut<{ success: boolean }>(
        `/api/v1/molecule/${record.mol_id}`,
        { project_root: projectRoot, ...record },
      )
      updated++
    } catch {
      failed.push(record.mol_id)
    }
  }
  return { updated, failed }
}
// ---- client.ts compatible wrappers ----

export interface MoleculeStats {
  total: number
  with_activity?: number
  pending?: number
}

// ============================================================================
// 化学信息学 (FastAPI 后端,通过 /api/v1/chem/* 路由访问 Python 侧 RDKit/chematic)
// ============================================================================


export interface SmilesValidation {
  valid: boolean
  canonical_smiles: string | null
  error: string | null
}

export async function chemValidateSmiles(smiles: string): Promise<SmilesValidation> {
  return invokeWithError(
    () => httpPost<SmilesValidation>('/api/v1/chem/validate-smiles', { smiles }),
    ErrorCode.ApiError,
  )
}

export interface ValidationIssue {
  code: string
  message: string
  severity: 'error' | 'warning'
}

export interface ValidateResponse {
  valid: boolean
  canonical_smiles: string | null
  issues: ValidationIssue[]
}

export async function validateSmiles(smiles: string): Promise<ValidateResponse> {
  const raw = await invokeWithError(
    () => httpPost<SmilesValidation>('/api/v1/chem/validate-smiles', { smiles }),
    ErrorCode.ApiError,
  )
  if (raw.valid) {
    return { valid: true, canonical_smiles: raw.canonical_smiles, issues: [] }
  }
  const message = raw.error ?? 'SMILES 解析失败'
  return {
    valid: false,
    canonical_smiles: raw.canonical_smiles,
    issues: [{ code: 'SYNTAX', severity: 'error', message }],
  }
}

export async function chemTanimotoSimilarity(smilesA: string, smilesB: string): Promise<number> {
  const resp = await invokeWithError(
    () => httpPost<{ similarity: number }>('/api/v1/chem/tanimoto', { smiles_a: smilesA, smiles_b: smilesB }),
    ErrorCode.ApiError,
  )
  return resp.similarity
}

export async function chemTanimotoBatchFilter(
  querySmiles: string,
  candidates: Array<[string, string]>,
  threshold = 0.5,
): Promise<Array<[string, string, number]>> {
  return invokeWithError(
    () => httpPost<Array<[string, string, number]>>('/api/v1/chem/substructure-search', {
      query: querySmiles,
      candidates,
      threshold,
    }),
    ErrorCode.ApiError,
  )
}

// ============================================================================
// MoleCode 转换 / 化学描述符
// ============================================================================

export interface ChemDescriptors {
  molecular_weight: number
  logp: number
  tpsa: number
  hba: number
  hbd: number
  rotatable_bonds: number
  formula: string
}

export async function chemDescriptors(smiles: string): Promise<ChemDescriptors> {
  return invokeWithError(
    () => httpPost<ChemDescriptors>('/api/v1/chem/properties', { smiles }),
    ErrorCode.ApiError,
  )
}

export async function esmilesToMolecode(esmiles: string, name: string): Promise<string> {
  return invokeWithError(
    () => httpPost<string>('/api/v1/chem/smiles-to-molecode', { smiles: esmiles, name }),
    ErrorCode.ApiError,
  )
}

// ============================================================================
// SAR 分析
// ============================================================================

export interface ScaffoldActivityRecord {
  mol_id: string
  esmiles: string
  name: string
  activity: number | null
  activity_type: string
  units: string
}

export interface ActivitySummary {
  count_with_activity: number
  count_without_activity: number
  min_activity: number | null
  max_activity: number | null
  mean_activity: number | null
}

export interface ScaffoldProfile {
  scaffold_esmiles: string
  molecule_count: number
  activities: ScaffoldActivityRecord[]
  activity_summary: ActivitySummary
}

export async function molScaffoldProfile(
  projectRoot: string,
  scaffoldEsmiles: string,
): Promise<ScaffoldProfile> {
  return invokeWithError(
    () => httpPost<ScaffoldProfile>('/api/v1/molecule/search', {
      project_root: projectRoot,
      query: scaffoldEsmiles,
    }),
    ErrorCode.ApiError,
  )
}

export interface ActivityCliff {
  mol_a_id: string
  mol_b_id: string
  mol_a_esmiles: string
  mol_b_esmiles: string
  mol_a_name: string
  mol_b_name: string
  similarity_score: number
  activity_a: number | null
  activity_b: number | null
  activity_ratio: number | null
  activity_type: string
}

export async function molFindActivityCliffs(
  projectRoot: string,
  minSimilarity: number,
  minActivityRatio: number,
): Promise<ActivityCliff[]> {
  return invokeWithError(
    () => httpPost<ActivityCliff[]>('/api/v1/molecule/search', {
      project_root: projectRoot,
      min_similarity: minSimilarity,
      min_activity_ratio: minActivityRatio,
    }),
    ErrorCode.ApiError,
  )
}

// ============================================================================
// 分子关系 / 聚类 / 高级分析
// ============================================================================

export interface MoleculeRelation {
  id?: number
  mol_a_id: string
  mol_b_id: string
  relation_type: 'similar' | 'same_as' | 'scaffold' | 'cluster'
  score: number | null
  metadata: Record<string, unknown> | null
  created_at: string
  [key: string]: unknown
}

export interface RelationStats {
  total: number
  similar: number
  same_as: number
  scaffold: number
  cluster: number
}

export interface ClusterInfo {
  cluster_id: string
  member_count: number
  members: string[]
  metadata: Record<string, unknown>
  [key: string]: unknown
}

export interface DedupPair {
  mol_a_id: string
  mol_b_id: string
  confidence: number
  reason: string
  [key: string]: unknown
}

export interface DedupResult {
  duplicates: DedupPair[]
  new_mols: string[]
  relations_added: number
}

export interface AnalogWithActivity {
  mol_id: string
  esmiles: string
  name: string
  similarity_score: number
  activity: number | null
  activity_type: string
  units: string
  [key: string]: unknown
}

export interface SubstructureMatch {
  mol_id: string
  esmiles: string
  [key: string]: unknown
}

// ---- 关系管理 (no HTTP route — kept for API compat) ----

export function molAddRelation(
  _molAId: string,
  _molBId: string,
  _relationType: string,
  _score?: number,
  _metadata?: Record<string, unknown>,
): Promise<number> {
  throw new Error('molAddRelation: no HTTP route available yet')
}

export function molDeleteRelation(_id: number): Promise<boolean> {
  throw new Error('molDeleteRelation: no HTTP route available yet')
}

export function molGetRelation(_id: number): Promise<MoleculeRelation | null> {
  throw new Error('molGetRelation: no HTTP route available yet')
}

export function molFindByMolecule(_molId: string): Promise<MoleculeRelation[]> {
  throw new Error('molFindByMolecule: no HTTP route available yet')
}

export function molFindSimilar(
  _molId: string,
  _minScore: number,
): Promise<Array<{ relation: MoleculeRelation; score: number }>> {
  throw new Error('molFindSimilar: no HTTP route available yet')
}

export function molFindSameAs(_molId: string): Promise<MoleculeRelation[]> {
  throw new Error('molFindSameAs: no HTTP route available yet')
}

export function molGetStats(): Promise<RelationStats> {
  throw new Error('molGetStats: no HTTP route available yet')
}

// ---- 聚类管理 ----

export function molAssignCluster(_molId: string, _clusterId: string): Promise<number> {
  throw new Error('molAssignCluster: no HTTP route available yet')
}

export function molRemoveFromCluster(_molId: string, _clusterId: string): Promise<boolean> {
  throw new Error('molRemoveFromCluster: no HTTP route available yet')
}

export function molGetClusterMembers(_clusterId: string): Promise<ClusterInfo> {
  throw new Error('molGetClusterMembers: no HTTP route available yet')
}

export function molGetMoleculeClusters(_molId: string): Promise<string[]> {
  throw new Error('molGetMoleculeClusters: no HTTP route available yet')
}

export function molListClusters(): Promise<ClusterInfo[]> {
  throw new Error('molListClusters: no HTTP route available yet')
}

// ---- 高级分析 ----

export function molFindAnalogsWithActivity(
  _molId: string,
  _minSimilarity: number,
): Promise<AnalogWithActivity[]> {
  throw new Error('molFindAnalogsWithActivity: no HTTP route available yet')
}

export function molDedupBatch(
  _newMols: Array<[string, string]>,
  _sameAsThreshold = 0.95,
): Promise<DedupResult> {
  throw new Error('molDedupBatch: no HTTP route available yet')
}

export function molSearchSubstructure(
  _querySmiles: string,
  _tanimotoThreshold?: number,
): Promise<SubstructureMatch[]> {
  throw new Error('molSearchSubstructure: no HTTP route available yet')
}
