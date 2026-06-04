import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

import { invoke } from '@tauri-apps/api/core'
import {
  chemValidateSmiles,
  chemTanimotoSimilarity,
  chemTanimotoBatchFilter,
  type SmilesValidation,
} from '../molecule'

const mockInvoke = vi.mocked(invoke)

describe('chem API (pure-Rust chematic)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('chemValidateSmiles', () => {
    it('returns valid result for a known SMILES', async () => {
      const stub: SmilesValidation = {
        valid: true,
        canonical_smiles: 'CCO',
        error: null,
      }
      mockInvoke.mockResolvedValue(stub)

      const result = await chemValidateSmiles('CCO')

      expect(result.valid).toBe(true)
      expect(result.canonical_smiles).toBe('CCO')
      expect(invoke).toHaveBeenCalledWith('chem_validate_smiles', { smiles: 'CCO' })
    })

    it('returns invalid result with error for malformed SMILES', async () => {
      const stub: SmilesValidation = {
        valid: false,
        canonical_smiles: null,
        error: 'SMILES parse failed: UnexpectedEnd',
      }
      mockInvoke.mockResolvedValue(stub)

      const result = await chemValidateSmiles('XYZ[')

      expect(result.valid).toBe(false)
      expect(result.canonical_smiles).toBeNull()
      expect(result.error).toMatch(/parse failed/)
    })
  })

  describe('chemTanimotoSimilarity', () => {
    it('passes both SMILES and returns f64 in [0, 1]', async () => {
      mockInvoke.mockResolvedValue(1.0)

      const result = await chemTanimotoSimilarity('CCO', 'CCO')

      expect(result).toBe(1.0)
      expect(invoke).toHaveBeenCalledWith('chem_tanimoto_similarity', {
        smilesA: 'CCO',
        smilesB: 'CCO',
      })
    })

    it('returns 0.0 for completely distinct molecules', async () => {
      mockInvoke.mockResolvedValue(0.05)

      const result = await chemTanimotoSimilarity('CCO', 'c1ccccc1')

      expect(result).toBeLessThan(0.5)
    })
  })

  describe('chemTanimotoBatchFilter', () => {
    it('forwards query, candidates, threshold and parses tuple list', async () => {
      const stub: Array<[string, string, number]> = [
        ['mol1', 'CCN', 0.9],
        ['mol2', 'c1ccccc1', 0.2],
      ]
      mockInvoke.mockResolvedValue(stub)

      const result = await chemTanimotoBatchFilter('CCO', [
        ['mol1', 'CCN'],
        ['mol2', 'c1ccccc1'],
      ], 0.5)

      expect(result).toHaveLength(2)
      expect(result[0][0]).toBe('mol1')
      expect(result[0][2]).toBeGreaterThan(0.5)
      expect(invoke).toHaveBeenCalledWith('chem_tanimoto_batch_filter', {
        querySmiles: 'CCO',
        candidates: [
          ['mol1', 'CCN'],
          ['mol2', 'c1ccccc1'],
        ],
        threshold: 0.5,
      })
    })

    it('uses default threshold 0.5 when omitted', async () => {
      mockInvoke.mockResolvedValue([])

      await chemTanimotoBatchFilter('CCO', [['x', 'C']])

      expect(invoke).toHaveBeenCalledWith('chem_tanimoto_batch_filter', {
        querySmiles: 'CCO',
        candidates: [['x', 'C']],
        threshold: 0.5,
      })
    })
  })
})
