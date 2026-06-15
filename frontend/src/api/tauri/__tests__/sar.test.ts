import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

import { invoke } from '@tauri-apps/api/core'
import {
  sarFindScaffold,
  sarDecompose,
  sarBuildMatrix,
  sarHeatmap,
  type ScaffoldResult,
  type RGroupDecomposition,
  type RGroupMatrix,
  type ActivityHeatmap,
  type CompoundInput,
} from '../sar'

const mockInvoke = vi.mocked(invoke)

describe('sar API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('sarFindScaffold', () => {
    it('calls sar_find_scaffold with the smiles list', async () => {
      const stub: ScaffoldResult = {
        scaffold_smarts: '[c]:0-[c]:1;[c]:1-[c]:2;[c]:2-[c]:3;[c]:3-[c]:4;[c]:4-[c]:5;[c]:5-[c]:0',
        atom_count: 6,
        bond_count: 6,
      }
      mockInvoke.mockResolvedValue(stub)

      const smilesList = ['c1ccc(CC(=O)O)cc1', 'c1ccc(CC(=O)N)cc1']
      const result = await sarFindScaffold(smilesList)

      expect(result).toEqual(stub)
      expect(invoke).toHaveBeenCalledWith('sar_find_scaffold', { smilesList })
    })

    it('returns null when no common scaffold is found', async () => {
      mockInvoke.mockResolvedValue(null)

      const result = await sarFindScaffold(['C', 'N'])

      expect(result).toBeNull()
      expect(invoke).toHaveBeenCalledWith('sar_find_scaffold', { smilesList: ['C', 'N'] })
    })
  })

  describe('sarDecompose', () => {
    it('calls sar_decompose with smiles and coreSmiles', async () => {
      const stub: RGroupDecomposition = {
        compound_id: '',
        compound_name: '',
        smiles: 'c1ccc(CC(=O)O)cc1',
        core_matches: true,
        r_groups: [
          { position: 0, label: 'R1', substituent_smiles: '[R1]', substituent_atoms: 2 },
        ],
      }
      mockInvoke.mockResolvedValue(stub)

      const result = await sarDecompose('c1ccc(CC(=O)O)cc1', 'c1ccccc1')

      expect(result).toEqual(stub)
      expect(invoke).toHaveBeenCalledWith('sar_decompose', {
        smiles: 'c1ccc(CC(=O)O)cc1',
        coreSmiles: 'c1ccccc1',
      })
    })
  })

  describe('sarBuildMatrix', () => {
    const compounds: CompoundInput[] = [
      { id: 'mol1', name: 'A', smiles: 'c1ccc(CC(=O)O)cc1', activity: 1.2 },
      { id: 'mol2', name: 'B', smiles: 'c1ccc(CC(=O)N)cc1', activity: 2.4 },
    ]

    it('calls sar_build_matrix with compounds and explicit coreSmiles', async () => {
      const stub: RGroupMatrix = {
        core_smiles: 'c1ccccc1',
        r_labels: ['R1'],
        rows: [['CC(=O)O'], ['CC(=O)N']],
        compounds: [
          { id: 'mol1', name: 'A', smiles: 'c1ccc(CC(=O)O)cc1', activity: 1.2, matches: true },
          { id: 'mol2', name: 'B', smiles: 'c1ccc(CC(=O)N)cc1', activity: 2.4, matches: true },
        ],
        unmatched_count: 0,
      }
      mockInvoke.mockResolvedValue(stub)

      const result = await sarBuildMatrix(compounds, 'c1ccccc1')

      expect(result).toEqual(stub)
      expect(invoke).toHaveBeenCalledWith('sar_build_matrix', {
        compounds,
        coreSmiles: 'c1ccccc1',
      })
    })

    it('passes null for coreSmiles when omitted', async () => {
      const stub: RGroupMatrix = {
        core_smiles: '',
        r_labels: [],
        rows: [],
        compounds: [
          { id: 'mol1', name: 'A', smiles: 'c1ccc(CC(=O)O)cc1', matches: false },
          { id: 'mol2', name: 'B', smiles: 'c1ccc(CC(=O)N)cc1', matches: false },
        ],
        unmatched_count: 2,
      }
      mockInvoke.mockResolvedValue(stub)

      const result = await sarBuildMatrix(compounds)

      expect(result).toEqual(stub)
      expect(invoke).toHaveBeenCalledWith('sar_build_matrix', {
        compounds,
        coreSmiles: null,
      })
    })
  })

  describe('sarHeatmap', () => {
    const matrix: RGroupMatrix = {
      core_smiles: 'c1ccccc1',
      r_labels: ['R1'],
      rows: [['CC(=O)O'], ['CC(=O)N']],
      compounds: [
        { id: 'mol1', name: 'A', smiles: 'c1ccc(CC(=O)O)cc1', activity: 1.2, matches: true },
        { id: 'mol2', name: 'B', smiles: 'c1ccc(CC(=O)N)cc1', activity: 2.4, matches: true },
      ],
      unmatched_count: 0,
    }

    it('calls sar_heatmap with matrix and lowerIsBetter true by default', async () => {
      const stub: ActivityHeatmap[] = [
        {
          r_label: 'R1',
          cells: [
            { substituent_smiles: 'CC(=O)O', avg_activity: 1.2, count: 1, min: 1.2, max: 1.2 },
            { substituent_smiles: 'CC(=O)N', avg_activity: 2.4, count: 1, min: 2.4, max: 2.4 },
          ],
        },
      ]
      mockInvoke.mockResolvedValue(stub)

      const result = await sarHeatmap(matrix)

      expect(result).toEqual(stub)
      expect(invoke).toHaveBeenCalledWith('sar_heatmap', {
        matrix,
        lowerIsBetter: true,
      })
    })

    it('passes explicit lowerIsBetter value', async () => {
      mockInvoke.mockResolvedValue([])

      await sarHeatmap(matrix, false)

      expect(invoke).toHaveBeenCalledWith('sar_heatmap', {
        matrix,
        lowerIsBetter: false,
      })
    })
  })
})
