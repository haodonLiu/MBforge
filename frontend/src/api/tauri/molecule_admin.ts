/** MoleculeEngine CRUD Tauri IPC wrappers. */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError } from './_utils'
import { ErrorCode } from '@/utils/errors'
import type { MoleculeRecord } from '@/types'
import type { MarkushOverlap, MarkushPattern } from './chem'

// ============================================================================
// 读
// ============================================================================

/** 按 mol_id 查询单条分子。 */
export async function molAdminGet(
  projectRoot: string,
  molId: string,
): Promise<MoleculeRecord | null> {
  return invokeWithError(
    () =>
      invoke<MoleculeRecord | null>('mol_admin_get', { projectRoot, molId }),
    ErrorCode.MoleculeSearch,
  )
}

/** 按 SMILES 精确查询。 */
export async function molAdminSearchBySmiles(
  projectRoot: string,
  smiles: string,
): Promise<MoleculeRecord | null> {
  return invokeWithError(
    () =>
      invoke<MoleculeRecord | null>('mol_admin_search_by_smiles', {
        projectRoot,
        smiles,
      }),
    ErrorCode.MoleculeSearch,
  )
}

/** FTS 全文搜索（name / notes / source_doc）。 */
export async function molAdminSearchText(
  projectRoot: string,
  query: string,
): Promise<MoleculeRecord[]> {
  return invokeWithError(
    () =>
      invoke<MoleculeRecord[]>('mol_admin_search_text', { projectRoot, query }),
    ErrorCode.MoleculeSearch,
  )
}

/** 分页列举（可选 source_type / status 过滤）。 */
export async function molAdminList(
  projectRoot: string,
  limit: number,
  offset: number,
  sourceType?: string,
  status?: string,
): Promise<MoleculeRecord[]> {
  return invokeWithError(
    () =>
      invoke<MoleculeRecord[]>('mol_admin_list', {
        projectRoot,
        limit,
        offset,
        sourceType,
        status,
      }),
    ErrorCode.MoleculeSearch,
  )
}

/** 库统计。 */
export async function molAdminStoreStats(
  projectRoot: string,
): Promise<Record<string, unknown>> {
  return invokeWithError(
    () =>
      invoke<Record<string, unknown>>('mol_admin_store_stats', { projectRoot }),
    ErrorCode.MoleculeSearch,
  )
}

/** Markush 覆盖度检查（engine wrapper；与 chemMarkushCheck 路径不同）。 */
export async function molAdminCheckMarkush(
  projectRoot: string,
  esmiles: string,
  query: string,
  ctx?: string,
): Promise<MarkushOverlap> {
  return invokeWithError(
    () =>
      invoke<MarkushOverlap>('mol_admin_check_markush', {
        projectRoot,
        esmiles,
        query,
        ctx,
      }),
    ErrorCode.MoleculeSearch,
  )
}

/** E-SMILES → MarkushPattern（engine wrapper）。 */
export async function molAdminParseEsmiles(
  projectRoot: string,
  input: string,
): Promise<MarkushPattern> {
  return invokeWithError(
    () =>
      invoke<MarkushPattern>('mol_admin_parse_esmiles', {
        projectRoot,
        input,
      }),
    ErrorCode.MoleculeSearch,
  )
}

// ============================================================================
// 写
// ============================================================================

/** 插入单条分子。 */
export async function molAdminAdd(
  projectRoot: string,
  record: MoleculeRecord,
): Promise<void> {
  await invokeWithError(
    () => invoke('mol_admin_add', { projectRoot, record }),
    ErrorCode.ApiError,
  )
}

/** 更新整条分子。 */
export async function molAdminUpdate(
  projectRoot: string,
  record: MoleculeRecord,
): Promise<boolean> {
  return invokeWithError(
    () => invoke<boolean>('mol_admin_update', { projectRoot, record }),
    ErrorCode.ApiError,
  )
}

/** 仅更新 status 字段。 */
export async function molAdminUpdateStatus(
  projectRoot: string,
  molId: string,
  status: string,
): Promise<boolean> {
  return invokeWithError(
    () =>
      invoke<boolean>('mol_admin_update_status', {
        projectRoot,
        molId,
        status,
      }),
    ErrorCode.ApiError,
  )
}

/** 物理删除单条分子。 */
export async function molAdminDelete(
  projectRoot: string,
  molId: string,
): Promise<boolean> {
  return invokeWithError(
    () =>
      invoke<boolean>('mol_admin_delete', { projectRoot, molId }),
    ErrorCode.ApiError,
  )
}

/** 添加相似度关系。 */
export async function molAdminAddSimilarity(
  projectRoot: string,
  molAId: string,
  molBId: string,
  score: number,
): Promise<number> {
  return invokeWithError(
    () =>
      invoke<number>('mol_admin_add_similarity', {
        projectRoot,
        molAId,
        molBId,
        score,
      }),
    ErrorCode.ApiError,
  )
}
