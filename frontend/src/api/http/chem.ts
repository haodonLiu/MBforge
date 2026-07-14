/** Cheminformatics pure-computation HTTP API wrappers. */

import { httpPost, invokeWithError } from './_utils'
import { ErrorCode } from '@/utils/errors'

// ============================================================================
// Envelope helper
// ============================================================================

/**
 * Chem endpoints return `{success: true, ...}` envelopes with the actual value
 * under `.result` (or other field). Callers MUST unwrap via this helper before
 * consuming the response — rendering an envelope object into JSX crashes React.
 */
type ChemEnvelope = { success: boolean; error?: string } & Record<string, unknown>

function unwrapChem<T>(raw: unknown, extract: (e: ChemEnvelope) => T): T {
  const env = raw as Record<string, unknown> | null
  if (env && typeof env === 'object' && env.success === true) {
    return extract(env as ChemEnvelope)
  }
  if (env && typeof env === 'object' && env.success === false) {
    throw new Error(typeof env.error === 'string' ? env.error : 'chem request failed')
  }
  // Backwards-compatible: if backend ever drops the envelope, return raw.
  return raw as T
}

// ============================================================================
// Types
// ============================================================================

/** E-SMILES 标签（前端表示） */
export interface EsTag {
  kind: 'atom' | 'ring' | 'circle'
  index: number
  value: string
}

/** 三层分离结果：纯 SMILES + 原始 E-SMILES + 语义标签 JSON */
export interface LayerSplit {
  smiles: string
  esmiles: string | null
  tags: Record<string, unknown> | null
}

/** 单条 SMILES 验证结果 */
export interface ValidateResult {
  input: string
  valid: boolean
  canonical_smiles: string | null
  error: string | null
}

/** PreprocessError DTO */
export interface PreprocessErrorDto {
  kind: 'empty' | 'too_long' | 'contains_spaces'
  message: string
}

/** Markush 解析结果（来自 markush.rs::MarkushPattern） */
export interface MarkushPattern {
  core_smiles: string
  r_groups: Array<{
    atom_index: number
    group_name: string
    definition: unknown
  }>
  abstract_rings: Array<{ index: number; name: string }>
  raw: string
}

/** Markush 覆盖度结果（来自 markush.rs::MarkushOverlap） */
export interface MarkushOverlap {
  match_level: 'FullOverlap' | 'PartialOverlap' | 'ScaffoldOverlap' | 'NoOverlap'
  core_overlap_ratio: number
  matched_core_atoms: number
  total_core_atoms: number
  r_group_results: Array<{
    group_name: string
    position: number
    query_substituent: string | null
    within_scope: boolean | null
    definition: string
  }>
  details: string[]
}

// ============================================================================
// Pure chem commands (no project state)
// ============================================================================

/** 标准化 SMILES（chematic 稳定化算法）。 */
export async function chemCanonicalize(smiles: string): Promise<string> {
  const raw = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/canonicalize', { smiles }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => e.result as string)
}

/** 子结构搜索：Tanimoto 预过滤 + VF2 精确验证。 */
export async function chemSubstructureSearch(
  query: string,
  candidates: Array<[string, string]>,
  threshold?: number,
): Promise<Array<[string, string, number]>> {
  const raw = await invokeWithError(
    () =>
      httpPost<unknown>('/api/v1/chem/substructure-search', {
        query,
        candidates,
        threshold,
      }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => e.results as Array<[string, string, number]>)
}

/** 纯 SMILES → MoleCode (Mermaid graph text)。 */
export async function chemSmilesToMolecode(
  smiles: string,
  name: string,
): Promise<string> {
  const raw = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/smiles-to-molecode', { smiles, name }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => e.result as string)
}

/** 给 SMILES 添加 E-SMILES 标签。 */
export async function chemSmilesToEsmiles(
  smiles: string,
  tags: EsTag[],
): Promise<string> {
  const raw = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/smiles-to-esmiles', { smiles, tags }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => e.result as string)
}

/** 从 E-SMILES 字符串中分离 SMILES + 标签列表。 */
export async function chemParseEsmilesTags(
  input: string,
): Promise<[string, EsTag[]]> {
  const raw = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/parse-esmiles-tags', { input }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => [e.smiles as string, e.tags as EsTag[]])
}

/** 清洗 LLM 污染的 E-SMILES。 */
export async function chemSanitizeEsmiles(raw: string): Promise<string> {
  const resp = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/sanitize-esmiles', { raw }),
    ErrorCode.ApiError,
  )
  return unwrapChem(resp, e => e.result as string)
}

/** 三层分离：纯 SMILES + 原始 E-SMILES + 语义标签 JSON。 */
export async function chemSeparateEsmilesLayers(
  input: string,
): Promise<LayerSplit> {
  const raw = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/separate-esmiles-layers', { input }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => ({
    smiles: e.smiles as string,
    esmiles: (e.esmiles ?? null) as string | null,
    tags: (e.tags ?? null) as Record<string, unknown> | null,
  }))
}

/**
 * 批量 SMILES 验证。
 * NOTE: `/validate-smiles` 返回 `{valid, error}` 形状（per-item 验证对象列表），
 * NOT `{success, result}`，所以不能套 `unwrapChem`。
 */
export async function chemValidateSmilesBatch(
  list: string[],
): Promise<ValidateResult[]> {
  return invokeWithError(
    () => httpPost<ValidateResult[]>('/api/v1/chem/validate-smiles', { list }),
    ErrorCode.ApiError,
  )
}

/** SMILES 文本级预处理（验证 + wildcard 归一化）。 */
export async function chemPreprocessSmiles(
  smiles: string,
): Promise<string> {
  const raw = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/preprocess-smiles', { smiles }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => e.result as string)
}

/** R-group 名称预处理（验证 + 缩写归一化）。 */
export async function chemPreprocessRgroupName(
  name: string,
): Promise<string> {
  const raw = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/preprocess-rgroup-name', { name }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => e.result as string)
}

/** E-SMILES → MarkushPattern。 */
export async function chemMarkushParse(
  input: string,
): Promise<MarkushPattern> {
  const raw = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/markush-parse', { input }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => ({
    core_smiles: e.core_smiles as string,
    r_groups: e.r_groups as MarkushPattern['r_groups'],
    abstract_rings: e.abstract_rings as MarkushPattern['abstract_rings'],
    raw: e.raw as string,
  }))
}

/** Markush 覆盖度检查（纯计算路径）。 */
export async function chemMarkushCheck(
  esmiles: string,
  query: string,
  ctx?: string,
): Promise<MarkushOverlap> {
  const raw = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/markush-check', { esmiles, query, ctx }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => ({
    match_level: e.match_level as MarkushOverlap['match_level'],
    core_overlap_ratio: e.core_overlap_ratio as number,
    matched_core_atoms: e.matched_core_atoms as number,
    total_core_atoms: e.total_core_atoms as number,
    r_group_results: e.r_group_results as MarkushOverlap['r_group_results'],
    details: e.details as string[],
  }))
}

/** 提取 E-SMILES 中的 core SMILES 部分。 */
export async function chemCoreSmiles(input: string): Promise<string> {
  const raw = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/core-smiles', { input }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => e.result as string)
}

/** GESim 原子级对齐：返回 [a→b, b→a] 双向索引序列。 */
export async function chemGesimAtomMapping(
  a: string,
  b: string,
): Promise<[Array<number | null>, Array<number | null>]> {
  const raw = await invokeWithError(
    () => httpPost<unknown>('/api/v1/chem/gesim-atom-mapping', { a, b }),
    ErrorCode.ApiError,
  )
  return unwrapChem(raw, e => [
    e.mapping_a as Array<number | null>,
    e.mapping_b as Array<number | null>,
  ])
}
