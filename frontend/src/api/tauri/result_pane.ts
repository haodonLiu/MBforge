/** Tauri commands backing the PDF viewer right-hand result pane.
 *
 * Wraps the Rust commands defined in
 * `src-tauri/src/commands/result_pane.rs` which back the spec in
 * `PDF_RESULT_PANE_API.md` §8.
 *
 * - `getMoleculeCorefChain` — list every cached occurrence of one molecule
 *   across the project, with bbox + text snippet per hit.
 * - `getPageParseResult` — structured text blocks + cached molecule
 *   detections + heuristic findings for a single page.
 */

import { invoke } from '@tauri-apps/api/core'

// ---------------------------------------------------------------------------
// §8.1 get_molecule_coref_chain
// ---------------------------------------------------------------------------

export interface CorefOccurrence {
  doc_id: string
  page: number
  bbox: [number, number, number, number]
  context: string
  confidence: number
  smiles: string
  esmiles: string
}

export interface CorefChain {
  mol_id: string
  occurrences: CorefOccurrence[]
  aliases: string[]
}

/** Cross-page coref chain for one molecule.
 *
 * `molId` is canonicalized (chematic) on the backend before matching.
 * E-SMILES values are reduced to the SMILES portion (before `<sep>`).
 */
export async function getMoleculeCorefChain(
  projectRoot: string,
  molId: string,
): Promise<CorefChain> {
  return invoke<CorefChain>('get_molecule_coref_chain', {
    projectRoot,
    molId,
  })
}

// ---------------------------------------------------------------------------
// §8.2 get_page_parse_result
// ---------------------------------------------------------------------------

export interface StructuredTextBlock {
  /** Always `"paragraph"` for now; reserved for `heading` / `table` / `figure`. */
  kind: string
  content: string
  bbox: [number, number, number, number]
}

export interface PageFinding {
  /** Currently always `"keyword"`. */
  kind: string
  text: string
  bbox: [number, number, number, number]
}

export interface PageParseResult {
  page: number
  structured_text: StructuredTextBlock[]
  /** Same shape as `CachedExtractPageResponse.results`. */
  molecules: unknown[]
  findings: PageFinding[]
}

/** Read the cached parse result for a single page: structured text +
 *  cached molecule detections + heuristic findings.
 *
 *  `pageHPts` is the page height in PDF points (bottom-left origin) used
 *  to flip the cached text-line coordinates.
 */
export async function getPageParseResult(params: {
  projectRoot: string
  docId: string
  page: number
  pageHPts: number
}): Promise<PageParseResult> {
  return invoke<PageParseResult>('get_page_parse_result', {
    projectRoot: params.projectRoot,
    docId: params.docId,
    page: params.page,
    pageHPts: params.pageHPts,
  })
}

// ---------------------------------------------------------------------------
// Coref 持久化（molecule ↔ label 配对，KB 存储）
// ---------------------------------------------------------------------------

/** 图内 OCR 检出的 label */
export interface FigureLabel {
  id: number
  doc_id: string
  page: number
  /** 归一化 bbox [x1, y1, x2, y2] in image coords (0-1) */
  label_bbox: [number, number, number, number]
  label_text: string
  ocr_conf: number
  image_path: string | null
}

/** 分子-标识符配对预测 */
export interface CorefPrediction {
  id: number
  doc_id: string
  page: number
  mol_smiles: string | null
  mol_bbox: [number, number, number, number] | null
  mol_conf: number | null
  label_id: number | null
  label_text: string | null
  label_bbox: [number, number, number, number] | null
  confidence: number
  /** 'geometric' | 'llm' | 'manual' */
  source: string
  is_confirmed: boolean
  /** 所属 figure 路径（persistence 时记录的 image_path，用于 bbox 投影） */
  image_path: string | null
}

/** 确保 (doc_id, page) 的 coref 标注存在（懒迁移入口） */
export interface EnsureCorefResult {
  doc_id: string
  page: number
  already_existed: boolean
  labels_written: number
  predictions_written: number
  error: string | null
}

/** 查 (doc, page) 所有 label 标注 */
export async function getFigureLabels(
  projectRoot: string,
  docId: string,
  page: number,
): Promise<FigureLabel[]> {
  return invoke<FigureLabel[]>('get_figure_labels', {
    projectRoot,
    docId,
    page,
  })
}

/** 查 (doc, page) 所有 coref 配对预测 */
export async function getCorefPredictions(
  projectRoot: string,
  docId: string,
  page: number,
): Promise<CorefPrediction[]> {
  return invoke<CorefPrediction[]>('get_coref_predictions', {
    projectRoot,
    docId,
    page,
  })
}

/** 确保 (doc, page) 的 coref 标注存在（懒迁移） */
export async function ensureCorefForImage(
  projectRoot: string,
  docId: string,
  page: number,
  imagePath: string,
): Promise<EnsureCorefResult> {
  return invoke<EnsureCorefResult>('ensure_coref_for_image', {
    projectRoot,
    docId,
    page,
    imagePath,
  })
}

/** 标记某 coref 预测为人工确认（或撤销） */
export async function confirmCorefPrediction(
  projectRoot: string,
  predictionId: number,
  isConfirmed: boolean,
): Promise<void> {
  await invoke('confirm_coref_prediction', {
    projectRoot,
    predictionId,
    isConfirmed,
  })
}

/** 人工重选 coref pair：删旧 + 写新，返回新 id */
export async function updateCorefPair(
  projectRoot: string,
  docId: string,
  page: number,
  oldPredictionId: number | null,
  molImageId: number | null,
  molSmiles: string | null,
  molBbox: [number, number, number, number] | null,
  labelId: number,
): Promise<number> {
  return invoke<number>('update_coref_pair', {
    projectRoot,
    docId,
    page,
    oldPredictionId,
    molImageId,
    molSmiles,
    molBbox,
    labelId,
  })
}
