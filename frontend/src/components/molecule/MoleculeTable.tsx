import { useTranslation } from 'react-i18next'
import type { MoleculeRecord } from '@/types'
import type {
  MoleculeSort,
  MoleculeSortField,
} from '@/hooks/useMoleculeLibrary'
import Skeleton from '@/components/ui/Skeleton'
import EmptyState from '@/components/ui/EmptyState'

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

  const handleCheckboxClick = (
    e: React.MouseEvent<HTMLInputElement>,
    molId: string,
  ) => {
    e.stopPropagation()
    if (e.shiftKey && lastClickedId) {
      onSelectRange(lastClickedId, molId)
    } else {
      onToggleSelect(molId)
      setLastClickedId(molId)
    }
  }

  const handleHeaderCheckboxChange = () => {
    if (allSelected) {
      molecules.forEach((m) => onToggleSelect(m.mol_id))
    } else {
      molecules.forEach((m) => {
        if (!selectedIds.has(m.mol_id)) onToggleSelect(m.mol_id)
      })
    }
  }

  const allSelected = molecules.length > 0 && molecules.every((m) => selectedIds.has(m.mol_id))

  if (loading) {
    return (
      <div style={{ padding: '16px 0' }}>
        <Skeleton variant="row" count={8} />
      </div>
    )
  }

  if (molecules.length === 0) {
    return <EmptyState message={t('mol.empty') ?? '暂无分子'} />
  }

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 10,
        overflow: 'auto',
        background: 'var(--bg-surface)',
      }}
    >
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border)' }}>
            <th style={{ padding: '10px 12px', width: 40, textAlign: 'center' }}>
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
                onClick={() => onSort(h.key)}
                style={{
                  padding: '10px 12px',
                  textAlign: 'left',
                  cursor: 'pointer',
                  userSelect: 'none',
                  color: 'var(--text-secondary)',
                  fontWeight: 600,
                }}
              >
                {h.label}
                {sort.field === h.key && (
                  <span style={{ marginLeft: 6, color: 'var(--accent)' }}>
                    {sort.direction === 'asc' ? '↑' : '↓'}
                  </span>
                )}
              </th>
            ))}
            <th style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--text-secondary)', fontWeight: 600 }}>
              Source
            </th>
          </tr>
        </thead>
        <tbody>
          {molecules.map((mol) => (
            <tr
              key={mol.mol_id}
              onClick={() => onRowClick(mol)}
              style={{
                borderBottom: '1px solid var(--border-subtle)',
                background: selectedIds.has(mol.mol_id) ? 'var(--accent-muted)' : undefined,
                cursor: 'pointer',
              }}
            >
              <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                <input
                  type="checkbox"
                  checked={selectedIds.has(mol.mol_id)}
                  onClick={(e) => handleCheckboxClick(e, mol.mol_id)}
                  aria-label={`Select ${mol.name || mol.mol_id}`}
                />
              </td>
              <td style={{ padding: '10px 12px' }}>
                <div style={{ fontWeight: 600 }}>{mol.name || mol.mol_id}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace', marginTop: 2 }}>
                  {mol.esmiles}
                </div>
              </td>
              <td style={{ padding: '10px 12px' }}>
                {mol.activity !== null && mol.activity !== undefined
                  ? `${mol.activity.toFixed(2)} ${mol.units || 'nM'}`
                  : '-'}
              </td>
              <td style={{ padding: '10px 12px' }}>
                <StatusBadge status={mol.status} />
              </td>
              <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>
                {new Date(mol.created_at).toLocaleDateString()}
              </td>
              <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>
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
  const colors: Record<string, { bg: string; text: string }> = {
    confirmed: { bg: 'var(--success-muted)', text: 'var(--success)' },
    pending: { bg: 'var(--warning-muted)', text: 'var(--warning)' },
    corrected: { bg: 'var(--info-muted)', text: 'var(--info)' },
    rejected: { bg: 'var(--danger-muted)', text: 'var(--danger)' },
  }
  const c = colors[status] || { bg: 'var(--bg-elevated)', text: 'var(--text-muted)' }
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 8px',
        borderRadius: 6,
        background: c.bg,
        color: c.text,
        fontSize: 11,
        fontWeight: 600,
        textTransform: 'capitalize',
      }}
    >
      {status}
    </span>
  )
}
