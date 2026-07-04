import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useMoleculeLibrary } from '../useMoleculeLibrary'

vi.mock('@/api/http/molecule_admin', () => ({
  molAdminList: vi.fn(),
  molAdminSearchText: vi.fn(),
}))

import { molAdminList } from '@/api/http/molecule_admin'

const mockMolecule = {
  mol_id: 'm1',
  name: 'A',
  esmiles: 'C',
  status: 'confirmed',
  activity: 10,
  activity_type: 'IC50',
  units: 'nM',
  source_doc: 'doc1',
  source_type: 'text',
  properties: {},
  tags: [],
  notes: '',
  created_at: '2026-01-01',
}

describe('useMoleculeLibrary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads molecules on mount', async () => {
    const molecules = [mockMolecule]
    const mockList = molAdminList as ReturnType<typeof vi.fn>
    mockList.mockResolvedValue(molecules)

    const { result } = renderHook(() => useMoleculeLibrary('/project'))

    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.molecules).toEqual(molecules)
    expect(result.current.totalCount).toBe(1)
    expect(result.current.error).toBeNull()
  })

  it('toggles selection', async () => {
    const molecules = [mockMolecule]
    const mockList = molAdminList as ReturnType<typeof vi.fn>
    mockList.mockResolvedValue(molecules)

    const { result } = renderHook(() => useMoleculeLibrary('/project'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.toggleSelection('m1')
    })
    expect(result.current.selectedIds.has('m1')).toBe(true)

    act(() => {
      result.current.toggleSelection('m1')
    })
    expect(result.current.selectedIds.has('m1')).toBe(false)
  })

  it('clears selection', async () => {
    const molecules = [
      mockMolecule,
      { ...mockMolecule, mol_id: 'm2', name: 'B' },
    ]
    const mockList = molAdminList as ReturnType<typeof vi.fn>
    mockList.mockResolvedValue(molecules)

    const { result } = renderHook(() => useMoleculeLibrary('/project'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.selectAll()
    })
    expect(result.current.selectedIds.size).toBe(2)

    act(() => {
      result.current.clearSelection()
    })
    expect(result.current.selectedIds.size).toBe(0)
  })
})
