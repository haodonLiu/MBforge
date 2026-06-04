/** GESim — graph-based molecular similarity (Rust-native, zero Python dep). */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

export interface GesimMappingResult {
  mapping1: number[]
  mapping2: number[]
}

/** Compute GESim similarity with logistic scaler (default, L=1, k=7, x0=0.4). */
export async function gesimSimilarity(smiles1: string, smiles2: string): Promise<number> {
  return invokeWithError(
    () => invoke<number>('gesim_similarity_cmd', { smiles1, smiles2 }),
    ErrorCode.MoleculeSearch,
  )
}

/** Compute raw GESim similarity (1 - QJS, no scaler). */
export async function gesimSimilarityRaw(smiles1: string, smiles2: string): Promise<number> {
  return invokeWithError(
    () => invoke<number>('gesim_similarity_raw_cmd', { smiles1, smiles2 }),
    ErrorCode.MoleculeSearch,
  )
}

/** Return atom-level match mapping between two molecules. */
export async function gesimMatchMapping(
  smiles1: string,
  smiles2: string,
): Promise<GesimMappingResult> {
  return invokeWithError(
    () => invoke<GesimMappingResult>('gesim_match_mapping_cmd', { smiles1, smiles2 }),
    ErrorCode.MoleculeSearch,
  )
}
