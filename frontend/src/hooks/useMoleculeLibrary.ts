import { useCallback, useEffect, useState } from 'react'
import { molAdminList, molAdminSearchText } from '@/api/http/molecule_admin'
import type { MoleculeRecord } from '@/types'

export type MoleculeStatusFilter = 'all' | 'confirmed' | 'pending' | 'rejected' | 'corrected'
export type MoleculeViewMode = 'table' | 'card'
export type MoleculeSortField = 'name' | 'activity' | 'status' | 'created_at'
export type MoleculeSortDirection = 'asc' | 'desc'

export interface MoleculeFilters {
  status: MoleculeStatusFilter
  sourceType: string
  sourceDoc: string
  activityMin: number | null
  activityMax: number | null
}

export interface MoleculePagination {
  page: number
  pageSize: number
}

export interface MoleculeSort {
  field: MoleculeSortField
  direction: MoleculeSortDirection
}

export interface UseMoleculeLibraryResult {
  molecules: MoleculeRecord[]
  totalCount: number
  loading: boolean
  error: string | null
  info: string | null
  query: string
  filters: MoleculeFilters
  sort: MoleculeSort
  pagination: MoleculePagination
  viewMode: MoleculeViewMode
  selectedIds: Set<string>

  setQuery: (q: string) => void
  setFilters: React.Dispatch<React.SetStateAction<MoleculeFilters>>
  setSort: (sort: MoleculeSort) => void
  setPagination: React.Dispatch<React.SetStateAction<MoleculePagination>>
  setViewMode: (mode: MoleculeViewMode) => void
  toggleSelection: (molId: string) => void
  selectRange: (startId: string, endId: string) => void
  selectAll: () => void
  clearSelection: () => void
  refresh: () => void
}

const VIEW_MODE_KEY = 'mbforge_molecule_view_mode'

export function useMoleculeLibrary(libraryRoot: string | null): UseMoleculeLibraryResult {
  const [molecules, setMolecules] = useState<MoleculeRecord[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [query, setQueryState] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState(query)
  const [filters, setFiltersState] = useState<MoleculeFilters>({
    status: 'all',
    sourceType: 'all',
    sourceDoc: 'all',
    activityMin: null,
    activityMax: null,
  })
  const [sort, setSortState] = useState<MoleculeSort>({ field: 'created_at', direction: 'desc' })
  const [pagination, setPaginationState] = useState<MoleculePagination>({ page: 1, pageSize: 50 })
  const [viewMode, setViewModeState] = useState<MoleculeViewMode>(() => {
    const saved = localStorage.getItem(VIEW_MODE_KEY)
    return saved === 'card' ? 'card' : 'table'
  })
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 250)
    return () => clearTimeout(timer)
  }, [query])

  const setQuery = useCallback((q: string) => {
    setQueryState(q)
    setPaginationState((prev) => ({ ...prev, page: 1 }))
  }, [])

  const setFilters = useCallback((update: React.SetStateAction<MoleculeFilters>) => {
    setFiltersState(update)
    setPaginationState((prev) => ({ ...prev, page: 1 }))
  }, [])

  const setSort = useCallback((nextSort: MoleculeSort) => {
    setSortState(nextSort)
    setPaginationState((prev) => ({ ...prev, page: 1 }))
  }, [])

  const setPagination = useCallback((update: React.SetStateAction<MoleculePagination>) => {
    setPaginationState((prev) => {
      const next = typeof update === 'function' ? update(prev) : update
      return next.pageSize !== prev.pageSize ? { ...next, page: 1 } : next
    })
  }, [])

  const setViewMode = useCallback((mode: MoleculeViewMode) => {
    localStorage.setItem(VIEW_MODE_KEY, mode)
    setViewModeState(mode)
  }, [])

  const load = useCallback(async () => {
    if (!libraryRoot) {
      setMolecules([])
      setTotalCount(0)
      return
    }
    setLoading(true)
    setError(null)
    try {
      let records: MoleculeRecord[]
      if (debouncedQuery.trim()) {
        records = await molAdminSearchText(libraryRoot, debouncedQuery.trim())
      } else {
        // Fetch the full dataset so client-side sorting/pagination work correctly.
        records = await molAdminList(
          libraryRoot,
          10000,
          0,
          filters.sourceType === 'all' ? undefined : filters.sourceType,
          filters.status === 'all' ? undefined : filters.status,
        )
      }

      if (!debouncedQuery.trim() && records.length >= 10000) {
        setInfo('mol.largeLibraryWarning')
      } else {
        setInfo(null)
      }

      let filtered = [...records]
      if (filters.status !== 'all') {
        filtered = filtered.filter((m) => m.status === filters.status)
      }
      if (filters.sourceType !== 'all') {
        filtered = filtered.filter((m) => m.source_type === filters.sourceType)
      }
      if (filters.sourceDoc !== 'all') {
        filtered = filtered.filter((m) => m.source_doc === filters.sourceDoc)
      }
      if (filters.activityMin !== null) {
        filtered = filtered.filter((m) => m.activity !== null && filters.activityMin !== null && m.activity >= filters.activityMin)
      }
      if (filters.activityMax !== null) {
        filtered = filtered.filter((m) => m.activity !== null && filters.activityMax !== null && m.activity <= filters.activityMax)
      }

      filtered.sort((a, b) => {
        const dir = sort.direction === 'asc' ? 1 : -1
        switch (sort.field) {
          case 'name':
            return (a.name || '').localeCompare(b.name || '') * dir
          case 'activity':
            if (a.activity === null && b.activity === null) return 0
            if (a.activity === null) return 1 * dir
            if (b.activity === null) return -1 * dir
            return (a.activity - b.activity) * dir
          case 'status':
            return (a.status || '').localeCompare(b.status || '') * dir
          case 'created_at':
          default:
            return (a.created_at || '').localeCompare(b.created_at || '') * dir
        }
      })

      const offset = (pagination.page - 1) * pagination.pageSize
      setMolecules(filtered.slice(offset, offset + pagination.pageSize))
      setTotalCount(filtered.length)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载分子失败')
      setInfo(null)
      setMolecules([])
      setTotalCount(0)
    } finally {
      setLoading(false)
    }
  }, [libraryRoot, debouncedQuery, filters, sort, pagination.page, pagination.pageSize])

  useEffect(() => {
    void load()
  }, [load])

  const toggleSelection = useCallback((molId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(molId)) next.delete(molId)
      else next.add(molId)
      return next
    })
  }, [])

  const selectRange = useCallback((startId: string, endId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      const startIdx = molecules.findIndex((m) => m.mol_id === startId)
      const endIdx = molecules.findIndex((m) => m.mol_id === endId)
      if (startIdx === -1 || endIdx === -1) return prev
      const [low, high] = startIdx < endIdx ? [startIdx, endIdx] : [endIdx, startIdx]
      for (let i = low; i <= high; i++) {
        next.add(molecules[i].mol_id)
      }
      return next
    })
  }, [molecules])

  const selectAll = useCallback(() => {
    setSelectedIds(new Set(molecules.map((m) => m.mol_id)))
  }, [molecules])

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set())
  }, [])

  return {
    molecules,
    totalCount,
    loading,
    error,
    info,
    query,
    filters,
    sort,
    pagination,
    viewMode,
    selectedIds,
    setQuery,
    setFilters,
    setSort,
    setPagination,
    setViewMode,
    toggleSelection,
    selectRange,
    selectAll,
    clearSelection,
    refresh: load,
  }
}
