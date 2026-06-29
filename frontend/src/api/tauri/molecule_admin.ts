/** MoleculeEngine CRUD HTTP API wrappers. */

import { httpPost, httpPut, httpDelete, invokeWithError } from './_utils'
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
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; molecule?: MoleculeRecord }>(
      '/api/v1/molecule/get',
      { project_root: projectRoot, mol_id: molId },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.success && resp.molecule ? resp.molecule : null
}

/** 按 SMILES 精确查询。 */
export async function molAdminSearchBySmiles(
  projectRoot: string,
  smiles: string,
): Promise<MoleculeRecord | null> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; results: MoleculeRecord[] }>(
      '/api/v1/molecule/search',
      { project_root: projectRoot, query: smiles },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.results[0] ?? null
}

/** FTS 全文搜索（name / notes / source_doc）。 */
export async function molAdminSearchText(
  projectRoot: string,
  query: string,
): Promise<MoleculeRecord[]> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; results: MoleculeRecord[] }>(
      '/api/v1/molecule/search',
      { project_root: projectRoot, query },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.results
}

/** 分页列举（可选 source_type / status 过滤）。 */
export async function molAdminList(
  projectRoot: string,
  limit: number,
  offset: number,
  _sourceType?: string,
  status?: string,
): Promise<MoleculeRecord[]> {
  const page = offset > 0 ? Math.floor(offset / limit) + 1 : 1
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; items: MoleculeRecord[]; total: number }>(
      '/api/v1/molecule/list',
      {
        project_root: projectRoot,
        page,
        page_size: limit,
        status: status ?? '',
      },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.items
}

/** 库统计。 */
export async function molAdminStoreStats(
  projectRoot: string,
): Promise<Record<string, unknown>> {
  return invokeWithError(
    () => httpPost<Record<string, unknown>>(
      '/api/v1/molecule/stats',
      { project_root: projectRoot },
    ),
    ErrorCode.MoleculeSearch,
  )
}

/** Markush 覆盖度检查。 */
export async function molAdminCheckMarkush(
  _projectRoot: string,
  esmiles: string,
  query: string,
  ctx?: string,
): Promise<MarkushOverlap> {
  return invokeWithError(
    () => httpPost<MarkushOverlap>('/api/v1/chem/markush-check', {
      esmiles,
      query,
      ctx,
    }),
    ErrorCode.MoleculeSearch,
  )
}

/** E-SMILES → MarkushPattern。 */
export async function molAdminParseEsmiles(
  _projectRoot: string,
  input: string,
): Promise<MarkushPattern> {
  return invokeWithError(
    () => httpPost<MarkushPattern>('/api/v1/chem/markush-parse', { input }),
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
    () => httpPost('/api/v1/molecule/create', {
      project_root: projectRoot,
      mol_id: record.mol_id,
      smiles: record.esmiles,
      esmiles: record.esmiles,
      name: record.name,
      source_type: record.source_type,
    }),
    ErrorCode.ApiError,
  )
}

/** 更新整条分子。 */
export async function molAdminUpdate(
  projectRoot: string,
  record: MoleculeRecord,
): Promise<boolean> {
  const resp = await invokeWithError(
    () => httpPut<{ success: boolean }>(
      `/api/v1/molecule/${record.mol_id}`,
      { project_root: projectRoot, ...record },
    ),
    ErrorCode.ApiError,
  )
  return resp.success
}

/** 仅更新 status 字段。 */
export async function molAdminUpdateStatus(
  projectRoot: string,
  molId: string,
  status: string,
): Promise<boolean> {
  const resp = await invokeWithError(
    () => httpPut<{ success: boolean }>(
      `/api/v1/molecule/${molId}`,
      { project_root: projectRoot, status },
    ),
    ErrorCode.ApiError,
  )
  return resp.success
}

/** 物理删除单条分子。 */
export async function molAdminDelete(
  projectRoot: string,
  molId: string,
): Promise<boolean> {
  const resp = await invokeWithError(
    () => httpDelete<{ success: boolean }>(
      `/api/v1/molecule/${molId}`,
      { project_root: projectRoot },
    ),
    ErrorCode.ApiError,
  )
  return resp.success
}

/** 添加相似度关系。 */
export function molAdminAddSimilarity(
  _projectRoot: string,
  _molAId: string,
  _molBId: string,
  _score: number,
): Promise<number> {
  throw new Error('molAdminAddSimilarity: no HTTP route available yet')
}
