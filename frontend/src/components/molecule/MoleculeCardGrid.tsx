import { useTranslation } from 'react-i18next'
import type { MoleculeRecord } from '@/types'
import { Card, CardGrid, Skeleton, EmptyState, Badge } from '@/components/ui'
import type { BadgeVariant } from '@/components/ui/Badge'
import MoleculeDisplay from './MoleculeDisplay'
import './MoleculeCardGrid.css'

export interface MoleculeCardGridProps {
  molecules: MoleculeRecord[]
  loading: boolean
  selectedIds: Set<string>
  onToggleSelect: (molId: string) => void
  onCardClick: (mol: MoleculeRecord) => void
}

const statusVariantMap: Record<string, BadgeVariant> = {
  confirmed: 'success',
  corrected: 'info',
  rejected: 'danger',
  pending: 'warning',
}

const statusLabelMap: Record<string, string> = {
  confirmed: 'Confirmed',
  corrected: 'Corrected',
  rejected: 'Rejected',
  pending: 'Pending',
}

export default function MoleculeCardGrid({
  molecules,
  loading,
  selectedIds,
  onToggleSelect,
  onCardClick,
}: MoleculeCardGridProps) {
  const { t } = useTranslation()

  if (loading) {
    return (
      <CardGrid minWidth={240} gap={16}>
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} variant="card" height={260} />
        ))}
      </CardGrid>
    )
  }

  if (molecules.length === 0) {
    return <EmptyState message={t('mol.empty') ?? '暂无分子'} />
  }

  return (
    <CardGrid minWidth={240} gap={16}>
      {molecules.map((mol) => {
        const isSelected = selectedIds.has(mol.mol_id)
        return (
          <Card
            key={mol.mol_id}
            hoverable
            padding={16}
            onClick={() => onCardClick(mol)}
            className="molecule-card"
            style={{
              borderColor: isSelected ? 'var(--accent)' : undefined,
              background: isSelected ? 'var(--accent-muted)' : undefined,
            }}
          >
            <input
              type="checkbox"
              checked={isSelected}
              onClick={(e) => e.stopPropagation()}
              onChange={() => onToggleSelect(mol.mol_id)}
              aria-label={`Select ${mol.name || mol.mol_id}`}
              className="molecule-card__checkbox"
            />
            <div className="molecule-card__badge">
              <Badge variant={statusVariantMap[mol.status] ?? 'warning'} dot>
                {t(`mol.status.${mol.status}`, { defaultValue: statusLabelMap[mol.status] })}
              </Badge>
            </div>

            <MoleculeDisplay
              smiles={mol.esmiles}
              name={mol.name || mol.mol_id}
              size={180}
              background="transparent"
            />

            <div style={{ marginTop: 12, textAlign: 'center' }}>
              <div
                className="molecule-card__name"
                title={mol.name || mol.mol_id}
              >
                {mol.name || mol.mol_id}
              </div>
              <div
                className="molecule-card__meta"
                title={mol.source_doc || undefined}
              >
                {mol.source_doc || '-'}
              </div>
              <div className="molecule-card__activity">
                {mol.activity !== null && mol.activity !== undefined
                  ? `${mol.activity.toFixed(2)} ${mol.units || 'nM'}`
                  : '-'}
              </div>
            </div>
          </Card>
        )
      })}
    </CardGrid>
  )
}
