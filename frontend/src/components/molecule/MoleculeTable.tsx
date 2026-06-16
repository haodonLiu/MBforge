import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import type { MoleculeRecord } from '@/types'
import type {
  MoleculeSort,
  MoleculeSortField,
} from '@/hooks/useMoleculeLibrary'
import Skeleton from '@/components/ui/Skeleton'
import EmptyState from '@/components/ui/EmptyState'
import './MoleculeTable.css'

interface MoleculeTableProps {
  molecules: MoleculeRecord[]
  loading: boolean
  selectedIds: Set<string>
  sort: MoleculeSort
  onSort: (field: MoleculeSortField) => void
  onToggleSelect: (molId: string) => void
  onSelectRange: (startId: string, endId: string) => void
  onRowClick: (mol: MoleculeRecord) => void
  lastClickedId: string | null
  setLastClickedId: (id: string | null) => void
}

const headers: { key: MoleculeSortField; label: string }[] = [
  { key: 'name', label: 'Name' },
  { key: 'activity', label: 'Activity' },
  { key: 'status', label: 'Status' },
  { key: 'created_at', label: 'Created' },
]

export default function MoleculeTable({
  molecules,
  loading,
  selectedIds,
  sort,
  onSort,
  onToggleSelect,
  onSelectRange,
  onRowClick,
  lastClickedId,
  setLastClickedId,
}: MoleculeTableProps) {
  const { t } = useTranslation()
  const shiftKeyRef = useRef(false)

  const allSelected = molecules.length > 0 && molecules.every((m) => selectedIds.has(m.mol_id))

  const handleHeaderCheckboxChange = () => {
    if (allSelected) {
      molecules.forEach((m) => onToggleSelect(m.mol_id))
    } else {
      molecules.forEach((m) => {
        if (!selectedIds.has(m.mol_id)) onToggleSelect(m.mol_id)
      })
    }
  }

  const handleCheckboxMouseDown = (e: React.MouseEvent<HTMLInputElement>) => {
    shiftKeyRef.current = e.shiftKey
  }

  const handleCheckboxClick = (e: React.MouseEvent<HTMLInputElement>) => {
    e.stopPropagation()
  }

  const handleCheckboxChange = (molId: string) => {
    if (shiftKeyRef.current && lastClickedId) {
      onSelectRange(lastClickedId, molId)
    } else {
      onToggleSelect(molId)
      setLastClickedId(molId)
    }
    shiftKeyRef.current = false
  }

  if (loading) {
    return (
      <div style={{ padding: '16px 0' }}>
        <Skeleton variant="row" count={8} />
      </div>
    )
  }

  if (molecules.length === 0) {
    return <EmptyState message={t('mol.empty')} />
  }

  return (
    <div className="molecule-table-wrapper">
      <table className="molecule-table">
        <thead>
          <tr className="molecule-table-header-row">
            <th className="molecule-table-checkbox-header" scope="col">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={handleHeaderCheckboxChange}
                aria-label="Select all molecules"
              />
            </th>
            {headers.map((h) => (
              <th
                key={h.key}
                scope="col"
                onClick={() => onSort(h.key)}
                className="molecule-table-header-cell"
              >
                {h.label}
                {sort.field === h.key && (
                  <span className="molecule-table-sort-indicator">
                    {sort.direction === 'asc' ? '↑' : '↓'}
                  </span>
                )}
              </th>
            ))}
            <th className="molecule-table-source-header" scope="col">
              Source
            </th>
          </tr>
        </thead>
        <tbody>
          {molecules.map((mol) => (
            <tr
              key={mol.mol_id}
              onClick={() => onRowClick(mol)}
              className={`molecule-table-row ${selectedIds.has(mol.mol_id) ? 'selected' : ''}`}
            >
              <td className="molecule-table-checkbox-cell">
                <input
                  type="checkbox"
                  checked={selectedIds.has(mol.mol_id)}
                  onMouseDown={handleCheckboxMouseDown}
                  onClick={handleCheckboxClick}
                  onChange={() => handleCheckboxChange(mol.mol_id)}
                  aria-label={`Select ${mol.name || mol.mol_id}`}
                />
              </td>
              <td className="molecule-table-cell">
                <div className="molecule-table-name">{mol.name || mol.mol_id}</div>
                <div className="molecule-table-esmiles">
                  {mol.esmiles}
                </div>
              </td>
              <td className="molecule-table-cell">
                {mol.activity !== null
                  ? `${mol.activity.toFixed(2)} ${mol.units || 'nM'}`
                  : '-'}
              </td>
              <td className="molecule-table-cell">
                <StatusBadge status={mol.status} />
              </td>
              <td className="molecule-table-cell molecule-table-muted-cell">
                {new Date(mol.created_at).toLocaleDateString()}
              </td>
              <td className="molecule-table-cell molecule-table-muted-cell">
                {mol.source_doc || '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colorClass: Record<string, string> = {
    confirmed: 'status-badge-confirmed',
    pending: 'status-badge-pending',
    corrected: 'status-badge-corrected',
    rejected: 'status-badge-rejected',
  }
  const badgeClass = colorClass[status] || 'status-badge-default'
  return (
    <span className={`status-badge ${badgeClass}`}>
      {status}
    </span>
  )
}
