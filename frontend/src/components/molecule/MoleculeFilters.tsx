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
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        padding: '12px 16px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <SearchIcon size={18} />
        <input
          type="text"
          value={localQuery}
          onChange={(e) => setLocalQuery(e.target.value)}
          placeholder={t('mol.search') ?? 'Search molecules'}
          disabled={disabled}
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            fontSize: 14,
            color: 'var(--text-primary)',
            fontFamily: 'inherit',
          }}
        />
        <Button variant="primary" size="sm" onClick={onSearch} disabled={disabled}>
          {t('mol.searchBtn') ?? 'Search'}
        </Button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <FilterIcon size={14} />
        <select
          value={filters.status}
          onChange={(e) => handleStatusChange(e.target.value as MoleculeFiltersType['status'])}
          disabled={disabled}
          style={{
            fontSize: 13,
            padding: '6px 10px',
            borderRadius: 6,
            border: '1px solid var(--border)',
            background: 'var(--bg-base)',
            color: 'var(--text-primary)',
          }}
        >
          <option value="all">{t('mol.status.all') ?? 'All statuses'}</option>
          <option value="confirmed">{t('mol.status.confirmed') ?? 'Confirmed'}</option>
          <option value="pending">{t('mol.status.pending') ?? 'Pending'}</option>
          <option value="corrected">{t('mol.status.corrected') ?? 'Corrected'}</option>
          <option value="rejected">{t('mol.status.rejected') ?? 'Rejected'}</option>
        </select>

        <select
          value={filters.sourceType}
          onChange={(e) =>
            onFiltersChange((prev) => ({ ...prev, sourceType: e.target.value }))
          }
          disabled={disabled}
          style={{
            fontSize: 13,
            padding: '6px 10px',
            borderRadius: 6,
            border: '1px solid var(--border)',
            background: 'var(--bg-base)',
            color: 'var(--text-primary)',
          }}
        >
          <option value="all">{t('mol.sourceType.all') ?? 'All source types'}</option>
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
          style={{
            fontSize: 13,
            padding: '6px 10px',
            borderRadius: 6,
            border: '1px solid var(--border)',
            background: 'var(--bg-base)',
            color: 'var(--text-primary)',
          }}
        >
          <option value="all">{t('mol.sourceDoc.all') ?? 'All source docs'}</option>
          {sourceDocOptions.map((doc) => (
            <option key={doc} value={doc}>{doc}</option>
          ))}
        </select>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
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
            style={{
              width: 90,
              fontSize: 13,
              padding: '6px 10px',
              borderRadius: 6,
              border: '1px solid var(--border)',
              background: 'var(--bg-base)',
              color: 'var(--text-primary)',
            }}
          />
          <span style={{ color: 'var(--text-muted)' }}>-</span>
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
            style={{
              width: 90,
              fontSize: 13,
              padding: '6px 10px',
              borderRadius: 6,
              border: '1px solid var(--border)',
              background: 'var(--bg-base)',
              color: 'var(--text-primary)',
            }}
          />
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          <button
            type="button"
            onClick={() => onViewModeChange('table')}
            disabled={disabled}
            style={{
              padding: 6,
              borderRadius: 6,
              border: 'none',
              background: viewMode === 'table' ? 'var(--accent-muted)' : 'transparent',
              color: viewMode === 'table' ? 'var(--accent)' : 'var(--text-secondary)',
              cursor: 'pointer',
            }}
            aria-label="Table view"
          >
            <TableIcon size={16} />
          </button>
          <button
            type="button"
            onClick={() => onViewModeChange('card')}
            disabled={disabled}
            style={{
              padding: 6,
              borderRadius: 6,
              border: 'none',
              background: viewMode === 'card' ? 'var(--accent-muted)' : 'transparent',
              color: viewMode === 'card' ? 'var(--accent)' : 'var(--text-secondary)',
              cursor: 'pointer',
            }}
            aria-label="Card view"
          >
            <GridIcon size={16} />
          </button>
        </div>
      </div>

      {filters.status === 'pending' && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '8px 12px',
            background: 'var(--warning-muted)',
            color: 'var(--warning)',
            borderRadius: 6,
            fontSize: 13,
          }}
        >
          <SparklesIcon size={14} />
          {t('mol.correctionMode') ?? 'OCR correction mode: click a row to open the correction panel'}
        </div>
      )}
    </div>
  )
}
