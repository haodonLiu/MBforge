/** MoleculeEngine CRUD HTTP API wrappers. */

import { httpPost, httpPut, httpDelete, invokeWithError } from './_utils'
import { ErrorCode } from '@/utils/errors'
import type { MoleculeRecord, EvidenceItem } from '@/types'
import type { MarkushOverlap, MarkushPattern } from './chem'

// ============================================================================
// 读
// ============================================================================

/** 按 mol_id 查询单条分子。 */
export async function molAdminGet(
  libraryRoot: string,
  molId: string,
): Promise<MoleculeRecord | null> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; molecule?: MoleculeRecord }>(
      '/api/v1/molecule/get',
      { library_root: libraryRoot, mol_id: molId },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.success && resp.molecule ? resp.molecule : null
}

/** 按 SMILES 精确查询。 */
export async function molAdminSearchBySmiles(
  libraryRoot: string,
  smiles: string,
): Promise<MoleculeRecord | null> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; results: MoleculeRecord[] }>(
      '/api/v1/molecule/search',
      { library_root: libraryRoot, query: smiles },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.results[0] ?? null
}

/** FTS 全文搜索（name / notes / source_doc）。 */
export async function molAdminSearchText(
  libraryRoot: string,
  query: string,
): Promise<MoleculeRecord[]> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; results: MoleculeRecord[] }>(
      '/api/v1/molecule/search',
      { library_root: libraryRoot, query },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.results
}

/** 分页列举（可选 source_type / status 过滤）。 */
export async function molAdminList(
  libraryRoot: string,
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
        library_root: libraryRoot,
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
  libraryRoot: string,
): Promise<Record<string, unknown>> {
  return invokeWithError(
    () => httpPost<Record<string, unknown>>(
      '/api/v1/molecule/stats',
      { library_root: libraryRoot },
    ),
    ErrorCode.MoleculeSearch,
  )
}

/** Return the full evidence chain for a canonical molecule. */
export async function molAdminEvidence(
  libraryRoot: string,
  canonicalSmiles: string,
): Promise<EvidenceItem[]> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; evidence: EvidenceItem[] }>(
      '/api/v1/molecule/evidence',
      { library_root: libraryRoot, canonical_smiles: canonicalSmiles },
    ),
    ErrorCode.MoleculeSearch,
  )
  return resp.evidence ?? []
}


/** Markush 覆盖度检查。 */
export async function molAdminCheckMarkush(
  _libraryRoot: string,
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
  _libraryRoot: string,
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
  libraryRoot: string,
  record: MoleculeRecord,
): Promise<void> {
  await invokeWithError(
    () => httpPost('/api/v1/molecule/create', {
      library_root: libraryRoot,
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
  libraryRoot: string,
  record: MoleculeRecord,
): Promise<boolean> {
  const resp = await invokeWithError(
    () => httpPut<{ success: boolean }>(
      `/api/v1/molecule/${record.mol_id}`,
      { library_root: libraryRoot, ...record },
    ),
    ErrorCode.ApiError,
  )
  return resp.success
}

/** 仅更新 status 字段。 */
export async function molAdminUpdateStatus(
  libraryRoot: string,
  molId: string,
  status: string,
): Promise<boolean> {
  const resp = await invokeWithError(
    () => httpPut<{ success: boolean }>(
      `/api/v1/molecule/${molId}`,
      { library_root: libraryRoot, status },
    ),
    ErrorCode.ApiError,
  )
  return resp.success
}

/** 物理删除单条分子。 */
export async function molAdminDelete(
  libraryRoot: string,
  molId: string,
): Promise<boolean> {
  const resp = await invokeWithError(
    () => httpDelete<{ success: boolean }>(
      `/api/v1/molecule/${molId}`,
      { library_root: libraryRoot },
    ),
    ErrorCode.ApiError,
  )
  return resp.success
}

/** 添加相似度关系。 */
export function molAdminAddSimilarity(
  _libraryRoot: string,
  _molAId: string,
  _molBId: string,
  _score: number,
): Promise<number> {
  throw new Error('molAdminAddSimilarity: no HTTP route available yet')
}
