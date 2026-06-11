/** Molecule store + analysis wrappers (compatible with client.ts). */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'
import type { MoleculeRecord } from '../../types'

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
  return invokeWithError(
    () => invoke<void>('mol_store_init', { projectRoot }),
    ErrorCode.MoleculeSearch,
  )
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
  return invokeWithError(
    () => invoke<void>('mol_store_add', {
      projectRoot,
      molId,
      esmiles,
      name: name ?? null,
      sourceDoc: sourceDoc ?? null,
      activity: activity ?? null,
      activityType: activityType ?? null,
      units: units ?? null,
      sourceType: sourceType ?? null,
    }),
    ErrorCode.MoleculeSearch,
  )
}

export async function molStoreList(
  projectRoot: string,
  limit?: number,
  offset?: number,
  sourceType?: string,
  status?: string,
): Promise<MoleculeRecord_[]> {
  return invokeWithError(
    () => invoke<MoleculeRecord_[]>('mol_store_list', {
      projectRoot,
      limit: limit ?? null,
      offset: offset ?? null,
      sourceType: sourceType ?? null,
      status: status ?? null,
    }),
    ErrorCode.MoleculeSearch,
  )
}

export async function molStoreGet(
  projectRoot: string,
  molId: string,
): Promise<MoleculeRecord_ | null> {
  return invokeWithError(
    () => invoke<MoleculeRecord_ | null>('mol_store_get', { projectRoot, molId }),
    ErrorCode.MoleculeSearch,
  )
}

export async function molStoreSearch(
  projectRoot: string,
  query: string,
): Promise<MoleculeRecord_[]> {
  return invokeWithError(
    () => invoke<MoleculeRecord_[]>('mol_store_search', { projectRoot, query }),
    ErrorCode.MoleculeSearch,
  )
}

export async function molStoreDelete(
  projectRoot: string,
  molId: string,
): Promise<boolean> {
  return invokeWithError(
    () => invoke<boolean>('mol_store_delete', { projectRoot, molId }),
    ErrorCode.MoleculeSearch,
  )
}

export async function molStoreStats(
  projectRoot: string,
): Promise<MolStoreStats> {
  return invokeWithError(
    () => invoke<MolStoreStats>('mol_store_stats', { projectRoot }),
    ErrorCode.MoleculeSearch,
  )
}

export async function molStoreSearchBySmiles(
  projectRoot: string,
  esmiles: string,
): Promise<MoleculeRecord_ | null> {
  return invokeWithError(
    () => invoke<MoleculeRecord_ | null>('mol_store_search_by_smiles', { projectRoot, smiles: esmiles }),
    ErrorCode.MoleculeSearch,
  )
}

export async function molStoreListByDoc(
  projectRoot: string,
  docId: string,
): Promise<MoleculeRecord_[]> {
  return invokeWithError(
    () => invoke<MoleculeRecord_[]>('mol_store_list_by_doc', { projectRoot, docId }),
    ErrorCode.MoleculeSearch,
  )
}

/** 更新单条分子记录（OCR 矫正后写回数据库用） */
export async function molStoreUpdate(
  projectRoot: string,
  record: MoleculeRecord_,
): Promise<boolean> {
  return invokeWithError(
    () => invoke<boolean>('mol_store_update', { projectRoot, record }),
    ErrorCode.MoleculeSearch,
  )
}

/** 批量更新多个分子. 返回 { updated: number, failed: string[] } */
export async function molStoreUpdateBatch(
  projectRoot: string,
  records: MoleculeRecord_[],
): Promise<{ updated: number; failed: string[] }> {
  return invokeWithError(
    () => invoke<{ updated: number; failed: string[] }>('mol_store_update_batch', {
      projectRoot,
      records,
    }),
    ErrorCode.MoleculeSearch,
  )
}
// ---- client.ts compatible wrappers ----

export interface MoleculeStats {
  total: number
  with_activity?: number
  pending?: number
}

/** 分子统计（与 client.ts moleculeStats 兼容的包装） */
export async function moleculeStatsTauri(
  projectRoot: string,
): Promise<{ success: boolean; stats: MoleculeStats; error?: string }> {
  try {
    const stats = await molStoreStats(projectRoot)
    return { success: true, stats: stats as unknown as MoleculeStats }
  } catch (e) {
    return { success: false, stats: { total: 0 }, error: String(e) }
  }
}

/** 列出分子（与 client.ts listMolecules 兼容的包装） */
export async function listMoleculesTauri(
  projectRoot: string,
  limit = 100,
  offset = 0,
): Promise<{ success: boolean; molecules: MoleculeRecord[]; error?: string }> {
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
): Promise<{ success: boolean; molecules: MoleculeRecord[]; error?: string }> {
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

// ============================================================================
// 纯 Rust chematic 化学信息学（无 Python sidecar）
// ============================================================================

/** SMILES 校验结果（与 Rust `SmilesValidation` 对应） */
export interface SmilesValidation {
  valid: boolean
  canonical_smiles: string | null
  error: string | null
}

/** 校验 SMILES — 纯 Rust，无后端依赖 */
export async function chemValidateSmiles(smiles: string): Promise<SmilesValidation> {
  return await invoke<SmilesValidation>('chem_validate_smiles', { smiles })
}

/** SMILES 校验 issue（用于 CorrectionPanel / MoleculeDisplay 的 issue 列表） */
export interface ValidationIssue {
  code: string
  message: string
  severity: 'error' | 'warning'
}

/** 校验 SMILES — 返回带 issue 列表的友好响应（用于 UI 展示） */
export interface ValidateResponse {
  valid: boolean
  canonical_smiles: string | null
  issues: ValidationIssue[]
}

/** 校验 SMILES — 纯 Rust，无后端依赖（返回带 issue 列表的友好格式） */
export async function validateSmiles(smiles: string): Promise<ValidateResponse> {
  const raw = await invoke<{ valid: boolean; canonical_smiles: string | null; error: string | null }>(
    'chem_validate_smiles',
    { smiles },
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

/** 计算两个 SMILES 之间的 Tanimoto 相似度（ECFP4，0.0–1.0） */
export async function chemTanimotoSimilarity(smilesA: string, smilesB: string): Promise<number> {
  return await invoke<number>('chem_tanimoto_similarity', { smilesA, smilesB })
}

/** 批量 Tanimoto 预过滤候选。
 *  返回 `[(mol_id, smiles, score), ...]`，按 score 降序 */
export async function chemTanimotoBatchFilter(
  querySmiles: string,
  candidates: Array<[string, string]>,
  threshold = 0.5,
): Promise<Array<[string, string, number]>> {
  return await invoke<Array<[string, string, number]>>('chem_tanimoto_batch_filter', {
    querySmiles,
    candidates,
    threshold,
  })
}

// ============================================================================
// MoleCode 转换 / 化学描述符（纯 Rust chematic-chem）
// ============================================================================

/** 分子理化性质描述符（MW / LogP / TPSA / HBA / HBD / rotatable / formula） */
export interface ChemDescriptors {
  molecular_weight: number
  logp: number
  tpsa: number
  hba: number
  hbd: number
  rotatable_bonds: number
  formula: string
}

/** 计算 SMILES 的理化性质。Rust 端 `chem_descriptors_cmd` (chematic-chem)。 */
export async function chemDescriptors(smiles: string): Promise<ChemDescriptors> {
  return invokeWithError(
    () => invoke<ChemDescriptors>('chem_descriptors_cmd', { smiles }),
    ErrorCode.ApiError,
  )
}

/** 把 E-SMILES / SMILES 转成 Mermaid MoleCode（含 Markush {R1} 节点）。 */
export async function esmilesToMolecode(esmiles: string, name: string): Promise<string> {
  return invokeWithError(
    () => invoke<string>('esmiles_to_molecode_cmd', { esmiles, name }),
    ErrorCode.ApiError,
  )
}

// ============================================================================
// SAR 分析：scaffold profile / activity cliffs
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

/** 按给定骨架 (e-smiles 子串) 聚合库内分子及其活性分布。 */
export async function molScaffoldProfile(
  projectRoot: string,
  scaffoldEsmiles: string,
): Promise<ScaffoldProfile> {
  return invokeWithError(
    () => invoke<ScaffoldProfile>('mol_scaffold_profile', { projectRoot, scaffoldEsmiles }),
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

/** 找活性悬崖 (结构相似但活性差异显著的分子对)。 */
export async function molFindActivityCliffs(
  projectRoot: string,
  minSimilarity: number,
  minActivityRatio: number,
): Promise<ActivityCliff[]> {
  return invokeWithError(
    () => invoke<ActivityCliff[]>('mol_find_activity_cliffs', {
      projectRoot,
      minSimilarity,
      minActivityRatio,
    }),
    ErrorCode.ApiError,
  )
}

// ============================================================================
// 分子关系 / 聚类 / 高级分析（对应 Rust commands/molecule.rs）
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

// ---- 关系管理 ----

export async function molAddRelation(
  molAId: string,
  molBId: string,
  relationType: string,
  score?: number,
  metadata?: Record<string, unknown>,
): Promise<number> {
  return invokeWithError(
    () => invoke<number>('mol_add_relation', {
      molAId,
      molBId,
      relationType,
      score: score ?? null,
      metadata: metadata ?? null,
    }),
    ErrorCode.ApiError,
  )
}

export async function molDeleteRelation(id: number): Promise<boolean> {
  return invokeWithError(
    () => invoke<boolean>('mol_delete_relation', { id }),
    ErrorCode.ApiError,
  )
}

export async function molGetRelation(id: number): Promise<MoleculeRelation | null> {
  return invokeWithError(
    () => invoke<MoleculeRelation | null>('mol_get_relation', { id }),
    ErrorCode.ApiError,
  )
}

export async function molFindByMolecule(molId: string): Promise<MoleculeRelation[]> {
  return invokeWithError(
    () => invoke<MoleculeRelation[]>('mol_find_by_molecule', { molId }),
    ErrorCode.ApiError,
  )
}

export async function molFindSimilar(
  molId: string,
  minScore: number,
): Promise<Array<{ relation: MoleculeRelation; score: number }>> {
  return invokeWithError(
    () => invoke<Array<[MoleculeRelation, number]>>('mol_find_similar', { molId, minScore }),
    ErrorCode.ApiError,
  ).then(rows => rows.map(([relation, score]) => ({ relation, score })))
}

export async function molFindSameAs(molId: string): Promise<MoleculeRelation[]> {
  return invokeWithError(
    () => invoke<MoleculeRelation[]>('mol_find_same_as', { molId }),
    ErrorCode.ApiError,
  )
}

export async function molGetStats(): Promise<RelationStats> {
  return invokeWithError(
    () => invoke<RelationStats>('mol_get_stats'),
    ErrorCode.ApiError,
  )
}

// ---- 聚类管理 ----

export async function molAssignCluster(molId: string, clusterId: string): Promise<number> {
  return invokeWithError(
    () => invoke<number>('mol_assign_cluster', { molId, clusterId }),
    ErrorCode.ApiError,
  )
}

export async function molRemoveFromCluster(molId: string, clusterId: string): Promise<boolean> {
  return invokeWithError(
    () => invoke<boolean>('mol_remove_from_cluster', { molId, clusterId }),
    ErrorCode.ApiError,
  )
}

export async function molGetClusterMembers(clusterId: string): Promise<ClusterInfo> {
  return invokeWithError(
    () => invoke<ClusterInfo>('mol_get_cluster_members', { clusterId }),
    ErrorCode.ApiError,
  )
}

export async function molGetMoleculeClusters(molId: string): Promise<string[]> {
  return invokeWithError(
    () => invoke<string[]>('mol_get_molecule_clusters', { molId }),
    ErrorCode.ApiError,
  )
}

export async function molListClusters(): Promise<ClusterInfo[]> {
  return invokeWithError(
    () => invoke<ClusterInfo[]>('mol_list_clusters'),
    ErrorCode.ApiError,
  )
}

// ---- 高级分析 ----

export async function molFindAnalogsWithActivity(
  molId: string,
  minSimilarity: number,
): Promise<AnalogWithActivity[]> {
  return invokeWithError(
    () => invoke<AnalogWithActivity[]>('mol_find_analogs_with_activity', { molId, minSimilarity }),
    ErrorCode.ApiError,
  )
}

export async function molDedupBatch(
  newMols: Array<[string, string]>,
  sameAsThreshold = 0.95,
): Promise<DedupResult> {
  return invokeWithError(
    () => invoke<DedupResult>('mol_dedup_batch', { newMols, sameAsThreshold }),
    ErrorCode.ApiError,
  )
}

export async function molSearchSubstructure(
  querySmiles: string,
  tanimotoThreshold?: number,
): Promise<SubstructureMatch[]> {
  return invokeWithError(
    () => invoke<SubstructureMatch[]>('mol_search_substructure', {
      querySmiles,
      tanimotoThreshold: tanimotoThreshold ?? null,
    }),
    ErrorCode.ApiError,
  )
}
