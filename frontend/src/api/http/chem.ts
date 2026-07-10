/** Cheminformatics pure-computation HTTP API wrappers. */

import { httpPost, invokeWithError } from './_utils'
import { ErrorCode } from '@/utils/errors'

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
  return invokeWithError(
    () => httpPost<string>('/api/v1/chem/canonicalize', { smiles }),
    ErrorCode.ApiError,
  )
}

/** 子结构搜索：Tanimoto 预过滤 + VF2 精确验证。 */
export async function chemSubstructureSearch(
  query: string,
  candidates: Array<[string, string]>,
  threshold?: number,
): Promise<Array<[string, string, number]>> {
  return invokeWithError(
    () => httpPost<Array<[string, string, number]>>('/api/v1/chem/substructure-search', {
      query,
      candidates,
      threshold,
    }),
    ErrorCode.ApiError,
  )
}

/** 纯 SMILES → MoleCode (Mermaid graph text)。 */
export async function chemSmilesToMolecode(
  smiles: string,
  name: string,
): Promise<string> {
  return invokeWithError(
    () => httpPost<string>('/api/v1/chem/smiles-to-molecode', { smiles, name }),
    ErrorCode.ApiError,
  )
}

/** 给 SMILES 添加 E-SMILES 标签。 */
export async function chemSmilesToEsmiles(
  smiles: string,
  tags: EsTag[],
): Promise<string> {
  return invokeWithError(
    () => httpPost<string>('/api/v1/chem/smiles-to-esmiles', { smiles, tags }),
    ErrorCode.ApiError,
  )
}

/** 从 E-SMILES 字符串中分离 SMILES + 标签列表。 */
export async function chemParseEsmilesTags(
  input: string,
): Promise<[string, EsTag[]]> {
  return invokeWithError(
    () => httpPost<[string, EsTag[]]>('/api/v1/chem/parse-esmiles-tags', { input }),
    ErrorCode.ApiError,
  )
}

/** 清洗 LLM 污染的 E-SMILES。 */
export async function chemSanitizeEsmiles(raw: string): Promise<string> {
  return invokeWithError(
    () => httpPost<string>('/api/v1/chem/sanitize-esmiles', { raw }),
    ErrorCode.ApiError,
  )
}

/** 三层分离：纯 SMILES + 原始 E-SMILES + 语义标签 JSON。 */
export async function chemSeparateEsmilesLayers(
  input: string,
): Promise<LayerSplit> {
  return invokeWithError(
    () => httpPost<LayerSplit>('/api/v1/chem/separate-esmiles-layers', { input }),
    ErrorCode.ApiError,
  )
}

/** 批量 SMILES 验证。 */
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
  return invokeWithError(
    () => httpPost<string>('/api/v1/chem/preprocess-smiles', { smiles }),
    ErrorCode.ApiError,
  )
}

/** R-group 名称预处理（验证 + 缩写归一化）。 */
export async function chemPreprocessRgroupName(
  name: string,
): Promise<string> {
  return invokeWithError(
    () => httpPost<string>('/api/v1/chem/preprocess-rgroup-name', { name }),
    ErrorCode.ApiError,
  )
}

/** E-SMILES → MarkushPattern。 */
export async function chemMarkushParse(
  input: string,
): Promise<MarkushPattern> {
  return invokeWithError(
    () => httpPost<MarkushPattern>('/api/v1/chem/markush-parse', { input }),
    ErrorCode.ApiError,
  )
}

/** Markush 覆盖度检查（纯计算路径）。 */
export async function chemMarkushCheck(
  esmiles: string,
  query: string,
  ctx?: string,
): Promise<MarkushOverlap> {
  return invokeWithError(
    () => httpPost<MarkushOverlap>('/api/v1/chem/markush-check', { esmiles, query, ctx }),
    ErrorCode.ApiError,
  )
}

/** 提取 E-SMILES 中的 core SMILES 部分。 */
export async function chemCoreSmiles(input: string): Promise<string> {
  return invokeWithError(
    () => httpPost<string>('/api/v1/chem/core-smiles', { input }),
    ErrorCode.ApiError,
  )
}

/** GESim 原子级对齐：返回 [a→b, b→a] 双向索引序列。 */
export async function chemGesimAtomMapping(
  a: string,
  b: string,
): Promise<[Array<number | null>, Array<number | null>]> {
  return invokeWithError(
    () =>
      httpPost<[Array<number | null>, Array<number | null>]>(
        '/api/v1/chem/gesim-atom-mapping',
        { a, b },
      ),
    ErrorCode.ApiError,
  )
}
