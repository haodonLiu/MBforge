import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Button from '@/components/ui/Button'
import {
  SearchIcon,
  FilterIcon,
  TableIcon,
  GridIcon,
  SparklesIcon,
} from '../icons'
import type {
  MoleculeFilters as MoleculeFiltersType,
  MoleculeViewMode,
} from '@/hooks/useMoleculeLibrary'

interface MoleculeFiltersProps {
  query: string
  onQueryChange: (q: string) => void
  filters: MoleculeFiltersType
  onFiltersChange: React.Dispatch<React.SetStateAction<MoleculeFiltersType>>
  viewMode: MoleculeViewMode
  onViewModeChange: (mode: MoleculeViewMode) => void
  onSearch: () => void
  sourceTypeOptions: string[]
  sourceDocOptions: string[]
  disabled?: boolean
}

export default function MoleculeFilters({
  query,
  onQueryChange,
  filters,
  onFiltersChange,
  viewMode,
  onViewModeChange,
  onSearch,
  sourceTypeOptions,
  sourceDocOptions,
  disabled = false,
}: MoleculeFiltersProps) {
  const { t } = useTranslation()
  const [localQuery, setLocalQuery] = useState(query)

  useEffect(() => {
    const timer = setTimeout(() => {
      if (localQuery !== query) {
        onQueryChange(localQuery)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [localQuery, query, onQueryChange])

  const handleStatusChange = (status: MoleculeFiltersType['status']) => {
    onFiltersChange((prev) => ({ ...prev, status }))
  }

  return (
    <div className="molecule-filters">
      <div className="molecule-filters__search-row">
        <SearchIcon size={18} />
        <input
          type="text"
          value={localQuery}
          onChange={(e) => setLocalQuery(e.target.value)}
          placeholder={t('mol.search')}
          disabled={disabled}
          className="molecule-filters__search-input"
        />
        <Button variant="primary" size="sm" onClick={onSearch} disabled={disabled}>
          {t('mol.searchBtn')}
        </Button>
      </div>

      <div className="molecule-filters__controls">
        <FilterIcon size={14} />
        <select
          value={filters.status}
          onChange={(e) => handleStatusChange(e.target.value as MoleculeFiltersType['status'])}
          disabled={disabled}
          className="molecule-filters__select"
        >
          <option value="all">{t('mol.status.all')}</option>
          <option value="confirmed">{t('mol.status.confirmed')}</option>
          <option value="pending">{t('mol.status.pending')}</option>
          <option value="corrected">{t('mol.status.corrected')}</option>
          <option value="rejected">{t('mol.status.rejected')}</option>
        </select>

        <select
          value={filters.sourceType}
          onChange={(e) =>
            onFiltersChange((prev) => ({ ...prev, sourceType: e.target.value }))
          }
          disabled={disabled}
          className="molecule-filters__select"
        >
          <option value="all">{t('mol.sourceType.all')}</option>
          {sourceTypeOptions.map((st) => (
            <option key={st} value={st}>{st}</option>
          ))}
        </select>

        <select
          value={filters.sourceDoc}
          onChange={(e) =>
            onFiltersChange((prev) => ({ ...prev, sourceDoc: e.target.value }))
          }
          disabled={disabled}
          className="molecule-filters__select"
        >
          <option value="all">{t('mol.sourceDoc.all')}</option>
          {sourceDocOptions.map((doc) => (
            <option key={doc} value={doc}>{doc}</option>
          ))}
        </select>

        <div className="molecule-filters__range">
          <input
            type="number"
            placeholder="Min activity"
            value={filters.activityMin ?? ''}
            onChange={(e) =>
              onFiltersChange((prev) => ({
                ...prev,
                activityMin: e.target.value === '' ? null : Number(e.target.value),
              }))
            }
            disabled={disabled}
            className="molecule-filters__range-input"
          />
          <span className="molecule-filters__range-separator">-</span>
          <input
            type="number"
            placeholder="Max activity"
            value={filters.activityMax ?? ''}
            onChange={(e) =>
              onFiltersChange((prev) => ({
                ...prev,
                activityMax: e.target.value === '' ? null : Number(e.target.value),
              }))
            }
            disabled={disabled}
            className="molecule-filters__range-input"
          />
        </div>

        <div className="molecule-filters__view-toggle" role="group" aria-label="View mode">
          <button
            type="button"
            onClick={() => onViewModeChange('table')}
            disabled={disabled}
            className={`molecule-filters__view-button${viewMode === 'table' ? ' is-active' : ''}`}
            aria-label="Table view"
            aria-pressed={viewMode === 'table'}
          >
            <TableIcon size={16} />
          </button>
          <button
            type="button"
            onClick={() => onViewModeChange('card')}
            disabled={disabled}
            className={`molecule-filters__view-button${viewMode === 'card' ? ' is-active' : ''}`}
            aria-label="Card view"
            aria-pressed={viewMode === 'card'}
          >
            <GridIcon size={16} />
          </button>
        </div>
      </div>

      {filters.status === 'pending' && (
        <div className="molecule-filters__correction">
          <SparklesIcon size={14} />
          {t('mol.correctionMode')}
        </div>
      )}
    </div>
  )
}
