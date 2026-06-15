import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

import { invoke } from '@tauri-apps/api/core'
import {
  molAdminGet,
  molAdminSearchBySmiles,
  molAdminSearchText,
  molAdminList,
  molAdminStoreStats,
  molAdminCheckMarkush,
  molAdminParseEsmiles,
  molAdminAdd,
  molAdminUpdate,
  molAdminUpdateStatus,
  molAdminDelete,
  molAdminAddSimilarity,
} from '../molecule_admin'

const mockInvoke = vi.mocked(invoke)

const mockRecord = {
  mol_id: 'mol-1',
  esmiles: 'CCO',
  name: 'ethanol',
  source_doc: 'doc-1',
  source_type: 'patent',
  activity: null,
  activity_type: '',
  units: '',
  status: 'pending',
  properties: {},
  tags: [],
  notes: '',
  created_at: '2026-06-15T00:00:00Z',
}

describe('moleculeAdmin API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('molAdminGet', () => {
    it('calls invoke with correct params', async () => {
      mockInvoke.mockResolvedValue(mockRecord)

      const result = await molAdminGet('/project', 'mol-1')

      expect(invoke).toHaveBeenCalledWith('mol_admin_get', {
        projectRoot: '/project',
        molId: 'mol-1',
      })
      expect(result).toEqual(mockRecord)
    })

    it('returns null when molecule not found', async () => {
      mockInvoke.mockResolvedValue(null)

      const result = await molAdminGet('/project', 'missing')

      expect(result).toBeNull()
    })

    it('propagates invoke errors', async () => {
      mockInvoke.mockRejectedValue(new Error('db locked'))

      await expect(molAdminGet('/project', 'mol-1')).rejects.toThrow('db locked')
    })
  })

  describe('molAdminSearchBySmiles', () => {
    it('calls invoke with correct params', async () => {
      mockInvoke.mockResolvedValue(mockRecord)

      const result = await molAdminSearchBySmiles('/project', 'CCO')

      expect(invoke).toHaveBeenCalledWith('mol_admin_search_by_smiles', {
        projectRoot: '/project',
        smiles: 'CCO',
      })
      expect(result).toEqual(mockRecord)
    })
  })

  describe('molAdminSearchText', () => {
    it('calls invoke with correct params', async () => {
      mockInvoke.mockResolvedValue([mockRecord])

      const result = await molAdminSearchText('/project', 'ethanol')

      expect(invoke).toHaveBeenCalledWith('mol_admin_search_text', {
        projectRoot: '/project',
        query: 'ethanol',
      })
      expect(result).toEqual([mockRecord])
    })
  })

  describe('molAdminList', () => {
    it('calls invoke with correct params', async () => {
      mockInvoke.mockResolvedValue([mockRecord])

      const result = await molAdminList('/project', 10, 0, 'patent', 'pending')

      expect(invoke).toHaveBeenCalledWith('mol_admin_list', {
        projectRoot: '/project',
        limit: 10,
        offset: 0,
        sourceType: 'patent',
        status: 'pending',
      })
      expect(result).toEqual([mockRecord])
    })

    it('works without optional filters', async () => {
      mockInvoke.mockResolvedValue([])

      await molAdminList('/project', 5, 0)

      expect(invoke).toHaveBeenCalledWith('mol_admin_list', {
        projectRoot: '/project',
        limit: 5,
        offset: 0,
        sourceType: undefined,
        status: undefined,
      })
    })
  })

  describe('molAdminStoreStats', () => {
    it('calls invoke with correct params', async () => {
      const stats = { total: 1, by_status: {} }
      mockInvoke.mockResolvedValue(stats)

      const result = await molAdminStoreStats('/project')

      expect(invoke).toHaveBeenCalledWith('mol_admin_store_stats', {
        projectRoot: '/project',
      })
      expect(result).toEqual(stats)
    })
  })

  describe('molAdminCheckMarkush', () => {
    it('calls invoke with correct params', async () => {
      const overlap = {
        match_level: 'FullOverlap',
        core_overlap_ratio: 1,
        matched_core_atoms: 6,
        total_core_atoms: 6,
        r_group_results: [],
        details: [],
      }
      mockInvoke.mockResolvedValue(overlap)

      const result = await molAdminCheckMarkush('/project', 'C*', 'CCO', 'ctx')

      expect(invoke).toHaveBeenCalledWith('mol_admin_check_markush', {
        projectRoot: '/project',
        esmiles: 'C*',
        query: 'CCO',
        ctx: 'ctx',
      })
      expect(result).toEqual(overlap)
    })

    it('works without optional ctx', async () => {
      mockInvoke.mockResolvedValue({ match_level: 'NoOverlap' })

      await molAdminCheckMarkush('/project', 'C*', 'CCO')

      expect(invoke).toHaveBeenCalledWith('mol_admin_check_markush', {
        projectRoot: '/project',
        esmiles: 'C*',
        query: 'CCO',
        ctx: undefined,
      })
    })
  })

  describe('molAdminParseEsmiles', () => {
    it('calls invoke with correct params', async () => {
      const pattern = {
        core_smiles: 'CCO',
        r_groups: [],
        abstract_rings: [],
        raw: 'CCO',
      }
      mockInvoke.mockResolvedValue(pattern)

      const result = await molAdminParseEsmiles('/project', 'CCO')

      expect(invoke).toHaveBeenCalledWith('mol_admin_parse_esmiles', {
        projectRoot: '/project',
        input: 'CCO',
      })
      expect(result).toEqual(pattern)
    })
  })

  describe('molAdminAdd', () => {
    it('calls invoke with correct params', async () => {
      mockInvoke.mockResolvedValue(undefined)

      await molAdminAdd('/project', mockRecord)

      expect(invoke).toHaveBeenCalledWith('mol_admin_add', {
        projectRoot: '/project',
        record: mockRecord,
      })
    })
  })

  describe('molAdminUpdate', () => {
    it('calls invoke with correct params', async () => {
      mockInvoke.mockResolvedValue(true)

      const result = await molAdminUpdate('/project', mockRecord)

      expect(invoke).toHaveBeenCalledWith('mol_admin_update', {
        projectRoot: '/project',
        record: mockRecord,
      })
      expect(result).toBe(true)
    })
  })

  describe('molAdminUpdateStatus', () => {
    it('calls invoke with correct params', async () => {
      mockInvoke.mockResolvedValue(true)

      const result = await molAdminUpdateStatus('/project', 'mol-1', 'confirmed')

      expect(invoke).toHaveBeenCalledWith('mol_admin_update_status', {
        projectRoot: '/project',
        molId: 'mol-1',
        status: 'confirmed',
      })
      expect(result).toBe(true)
    })
  })

  describe('molAdminDelete', () => {
    it('calls invoke with correct params', async () => {
      mockInvoke.mockResolvedValue(true)

      const result = await molAdminDelete('/project', 'mol-1')

      expect(invoke).toHaveBeenCalledWith('mol_admin_delete', {
        projectRoot: '/project',
        molId: 'mol-1',
      })
      expect(result).toBe(true)
    })
  })

  describe('molAdminAddSimilarity', () => {
    it('calls invoke with correct params', async () => {
      mockInvoke.mockResolvedValue(1)

      const result = await molAdminAddSimilarity('/project', 'mol-a', 'mol-b', 0.85)

      expect(invoke).toHaveBeenCalledWith('mol_admin_add_similarity', {
        projectRoot: '/project',
        molAId: 'mol-a',
        molBId: 'mol-b',
        score: 0.85,
      })
      expect(result).toBe(1)
    })
  })
})
