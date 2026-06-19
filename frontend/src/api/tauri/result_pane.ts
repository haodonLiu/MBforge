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
