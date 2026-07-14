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
import { SparklesIcon } from '@/components/icons'
import type { MoleculeRecord } from '@/types'
import type { MoleculeSortField } from '@/hooks/useMoleculeLibrary'
import './molecule/MoleculeLibrary.css'

export default function MoleculeLibrary() {
  const { libraryRoot } = useAppContext()
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
  } = useMoleculeLibrary(libraryRoot)

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
  const [isAnalysisOpen, setIsAnalysisOpen] = useState(false)

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
      <section className="molecule-library-page">
        <header className="molecule-library-page__header">
          <div className="molecule-library-page__heading">
            <PageTitle>{t('mol.title')}</PageTitle>
            <span className="molecule-library-page__count">{totalCount.toLocaleString()}</span>
          </div>
          <div className="molecule-library-page__header-actions">
            <Button
              variant="secondary"
              size="sm"
              icon={<SparklesIcon size={15} />}
              onClick={() => setIsAnalysisOpen((open) => !open)}
              disabled={!isAnalysisOpen && selectedIds.size === 0}
            >
              {isAnalysisOpen ? 'Hide analysis' : 'Analyze selection'}
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowAddDialog(true)}
              disabled={!libraryRoot}
            >
              {t('mol.add')}
            </Button>
          </div>
        </header>

        <div className={`molecule-library-workbench${isAnalysisOpen ? ' has-analysis' : ''}`}>
          <main className="molecule-library-results">
            <section className="molecule-library-filters">
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
            </section>

            <section className="molecule-library-results__body">
              <div className="molecule-library-results__summary">
                <span>{totalCount.toLocaleString()}</span>
                <span className="molecule-library-results__summary-label">results</span>
                {selectedIds.size > 0 && (
                  <span className="molecule-library-results__selection-count">
                    {selectedIds.size} selected
                  </span>
                )}
              </div>

              <div className="molecule-library-results__scroll-area">
                {info && (
                  <div className="molecule-library-notice" role="status">
                    {t(info, { limit: 10000 })}
                  </div>
                )}
                {error ? (
                  <div className="molecule-library-error" role="alert">{error}</div>
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
            </section>

            <footer className="molecule-library-results__footer">
              <div className="molecule-library-pagination">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setPagination((page) => ({ ...page, page: page.page - 1 }))}
                  disabled={loading || pagination.page <= 1}
                >
                  {t('mol.previous')}
                </Button>
                <span className="molecule-library-pagination__summary">
                  {t('mol.pageInfo', { current: pagination.page, total: totalPages })}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setPagination((page) => ({ ...page, page: page.page + 1 }))}
                  disabled={loading || pagination.page >= totalPages}
                >
                  {t('mol.next')}
                </Button>
                <label className="molecule-library-page-size" htmlFor="page-size">
                  <span>{t('mol.pageSize')}</span>
                  <select
                    id="page-size"
                    value={pagination.pageSize}
                    onChange={(event) =>
                      setPagination({ ...pagination, pageSize: Number(event.target.value) })
                    }
                    disabled={loading}
                  >
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                    <option value={200}>200</option>
                  </select>
                </label>
              </div>

              <div className="molecule-library-selection-actions">
                <span className="molecule-library-selection-actions__summary">
                  {t('mol.selectionSummary', { count: selectedIds.size, total: totalCount })}
                </span>
                <Button variant="ghost" size="sm" onClick={selectAll} disabled={loading}>
                  {t('mol.selectAll')}
                </Button>
                <Button variant="ghost" size="sm" onClick={clearSelection} disabled={selectedIds.size === 0}>
                  {t('mol.clearSelection')}
                </Button>
              </div>
            </footer>
          </main>

          {isAnalysisOpen && (
            <aside className="molecule-library-analysis" aria-label="Molecule analysis">
              <div className="molecule-library-analysis__header">
                <div>
                  <span className="molecule-library-analysis__eyebrow">Selection workspace</span>
                  <h2>Analysis</h2>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setIsAnalysisOpen(false)}>
                  Close
                </Button>
              </div>
              <div className="molecule-library-analysis__content">
                <MoleculeAnalysisPanel
                  analysisInput={analysisInput}
                  sarSession={sarSession}
                  activeTab={activeTab}
                  onTabChange={(tab) => setActiveTab(tab)}
                  libraryRoot={libraryRoot}
                  onRefresh={refresh}
                />
              </div>
            </aside>
          )}
        </div>
      </section>

      {libraryRoot && (
        <AddMoleculeDialog
          open={showAddDialog}
          onClose={() => setShowAddDialog(false)}
          libraryRoot={libraryRoot}
          onAdded={handleSaved}
        />
      )}

      <MoleculeDetailDrawer
        molecule={selectedMolecule}
        open={drawerOpen}
        libraryRoot={libraryRoot}
        onClose={handleDrawerClose}
        onSaved={handleSaved}
      />
    </PageContainer>
  )
}
