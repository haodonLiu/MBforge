import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import PageContainer from '@/components/ui/PageContainer'
import PageTitle from '@/components/ui/PageTitle'
import Button from '@/components/ui/Button'
import { AddMoleculeDialog } from '@/components/ui/AddMoleculeDialog'
import { useAppContext } from '@/context/AppContext'
import { useMoleculeLibrary } from '@/hooks/useMoleculeLibrary'
import { useMoleculeAnalysis } from '@/hooks/useMoleculeAnalysis'
import MoleculeFiltersComponent from '@/components/molecule/MoleculeFilters'
import MoleculeTable from '@/components/molecule/MoleculeTable'
import MoleculeCardGrid from '@/components/molecule/MoleculeCardGrid'
import MoleculeAnalysisPanel from '@/components/molecule/MoleculeAnalysisPanel'
import MoleculeDetailDrawer from '@/components/molecule/MoleculeDetailDrawer'
import type { MoleculeRecord } from '@/types'
import type { MoleculeSortField } from '@/hooks/useMoleculeLibrary'

export default function MoleculeLibrary() {
  const { projectRoot } = useAppContext()
  const { t } = useTranslation()

  const {
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
    isCorrectionMode,
    setQuery,
    setFilters,
    setSort,
    setPagination,
    setViewMode,
    toggleSelection,
    selectRange,
    selectAll,
    clearSelection,
    refresh,
  } = useMoleculeLibrary(projectRoot)

  const {
    activeTab,
    setActiveTab,
    analysisInput,
    sarSession,
  } = useMoleculeAnalysis(molecules, selectedIds)

  const [selectedMolecule, setSelectedMolecule] = useState<MoleculeRecord | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [lastClickedId, setLastClickedId] = useState<string | null>(null)
  const [showAddDialog, setShowAddDialog] = useState(false)

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(totalCount / pagination.pageSize)),
    [totalCount, pagination.pageSize],
  )

  const sourceTypeOptions = useMemo(
    () => Array.from(new Set(molecules.map((m) => m.source_type).filter(Boolean))),
    [molecules],
  )

  const sourceDocOptions = useMemo(
    () => Array.from(new Set(molecules.map((m) => m.source_doc).filter(Boolean))),
    [molecules],
  )

  const handleSort = (field: MoleculeSortField) => {
    setSort({
      field,
      direction: sort.field === field && sort.direction === 'asc' ? 'desc' : 'asc',
    })
  }

  const handleRowClick = (mol: MoleculeRecord) => {
    setSelectedMolecule(mol)
    setDrawerOpen(true)
  }

  const handleDrawerClose = () => {
    setDrawerOpen(false)
    setSelectedMolecule(null)
  }

  const handleSaved = () => {
    refresh()
  }

  return (
    <PageContainer>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '16px',
        }}
      >
        <PageTitle>{t('mol.title')}</PageTitle>
      </div>

      <div
        style={{
          display: 'flex',
          gap: '16px',
          height: 'calc(100vh - 180px)',
          minHeight: 0,
        }}
      >
        {/* Left column */}
        <div
          style={{
            width: '40%',
            minWidth: '360px',
            maxWidth: '50%',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            minHeight: 0,
          }}
        >
          <MoleculeFiltersComponent
            query={query}
            onQueryChange={setQuery}
            filters={filters}
            onFiltersChange={setFilters}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            onSearch={refresh}
            sourceTypeOptions={sourceTypeOptions}
            sourceDocOptions={sourceDocOptions}
            disabled={loading}
          />

          <div
            style={{
              flex: 1,
              overflow: 'auto',
              minHeight: 0,
            }}
          >
            {info && (
              <div
                style={{
                  padding: '12px 16px',
                  marginBottom: '12px',
                  color: 'var(--warning)',
                  background: 'rgba(from var(--warning) r g b / 0.1)',
                  border: '1px solid rgba(from var(--warning) r g b / 0.3)',
                  borderRadius: '8px',
                  fontSize: '13px',
                }}
              >
                {info ? t(info, { limit: 10000 }) : null}
              </div>
            )}
            {error ? (
              <div
                style={{
                  padding: '16px',
                  color: 'var(--danger)',
                  background: 'var(--danger-muted)',
                  borderRadius: '8px',
                }}
              >
                {error}
              </div>
            ) : viewMode === 'table' ? (
              <MoleculeTable
                molecules={molecules}
                loading={loading}
                selectedIds={selectedIds}
                sort={sort}
                onSort={handleSort}
                onToggleSelect={toggleSelection}
                onSelectRange={selectRange}
                onRowClick={handleRowClick}
                lastClickedId={lastClickedId}
                setLastClickedId={setLastClickedId}
              />
            ) : (
              <MoleculeCardGrid
                molecules={molecules}
                loading={loading}
                selectedIds={selectedIds}
                onToggleSelect={toggleSelection}
                onCardClick={handleRowClick}
              />
            )}
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
              padding: '10px 16px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: '10px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setPagination((p) => ({ ...p, page: p.page - 1 }))}
                disabled={loading || pagination.page <= 1}
              >
                {t('mol.previous')}
              </Button>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                {t('mol.pageInfo', { current: pagination.page, total: totalPages })}
              </span>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setPagination((p) => ({ ...p, page: p.page + 1 }))}
                disabled={loading || pagination.page >= totalPages}
              >
                {t('mol.next')}
              </Button>
            </div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '13px',
                color: 'var(--text-secondary)',
              }}
            >
              <label htmlFor="page-size">{t('mol.pageSize')}</label>
              <select
                id="page-size"
                value={pagination.pageSize}
                onChange={(e) =>
                  setPagination({ ...pagination, pageSize: Number(e.target.value) })
                }
                disabled={loading}
                style={{
                  padding: '4px 8px',
                  borderRadius: 6,
                  border: '1px solid var(--border)',
                  background: 'var(--bg-base)',
                  color: 'var(--text-primary)',
                  fontSize: 13,
                }}
              >
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={200}>200</option>
              </select>
            </div>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
              padding: '12px 16px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: '10px',
            }}
          >
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              {t('mol.selectionSummary', {
                selected: selectedIds.size,
                total: totalCount,
              })}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Button variant="secondary" size="sm" onClick={selectAll} disabled={loading}>
                {t('mol.selectAll')}
              </Button>
              <Button variant="secondary" size="sm" onClick={clearSelection} disabled={selectedIds.size === 0}>
                {t('mol.clearSelection')}
              </Button>
              <Button variant="primary" size="sm" onClick={() => setShowAddDialog(true)} disabled={!projectRoot}>
                {t('mol.add')}
              </Button>
            </div>
          </div>
        </div>

        {/* Right column */}
        <div
          style={{
            flex: 1,
            minWidth: 0,
            minHeight: 0,
            overflow: 'auto',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: '10px',
            padding: '16px',
          }}
        >
          <MoleculeAnalysisPanel
            analysisInput={analysisInput}
            sarSession={sarSession}
            activeTab={activeTab}
            onTabChange={(tab) => setActiveTab(tab)}
            projectRoot={projectRoot}
            onRefresh={refresh}
          />
        </div>
      </div>

      {projectRoot && (
        <AddMoleculeDialog
          open={showAddDialog}
          onClose={() => setShowAddDialog(false)}
          projectRoot={projectRoot}
          onAdded={handleSaved}
        />
      )}

      <MoleculeDetailDrawer
        molecule={selectedMolecule}
        open={drawerOpen}
        isCorrectionMode={isCorrectionMode}
        projectRoot={projectRoot}
        onClose={handleDrawerClose}
        onSaved={handleSaved}
      />
    </PageContainer>
  )
}
