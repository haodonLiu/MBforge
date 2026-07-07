import Button from '../ui/Button'
import CorrectionPanel, { type CorrectionItem } from './CorrectionPanel'
import MoleculeDetailPanel from './MoleculeDetailPanel'
import { molAdminUpdate } from '@/api/http/molecule_admin'
import { showToast } from '@/hooks/useToast'
import type { MoleculeRecord } from '../../types'

interface MoleculeDetailDrawerProps {
  molecule: MoleculeRecord | null
  open: boolean
  isCorrectionMode: boolean
  libraryRoot: string | null
  onClose: () => void
  onSaved?: () => void
}

function CloseIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function buildCorrectionItem(molecule: MoleculeRecord): CorrectionItem {
  const status = (['pending', 'confirmed', 'rejected', 'corrected'].includes(molecule.status)
    ? molecule.status
    : 'pending') as CorrectionItem['status']

  return {
    id: molecule.mol_id,
    ocrSmiles: molecule.esmiles,
    ocrConfidence: 0.5,
    name: molecule.name || undefined,
    sourceDoc: molecule.source_doc || undefined,
    context: molecule.notes || undefined,
    sourceImage: typeof molecule.properties?.mol_img_path === 'string'
      ? molecule.properties.mol_img_path
      : undefined,
    status,
  }
}

export default function MoleculeDetailDrawer({
  molecule,
  open,
  isCorrectionMode,
  libraryRoot,
  onClose,
  onSaved,
}: MoleculeDetailDrawerProps) {
  if (!open || !molecule) return null

  const title = isCorrectionMode ? 'OCR 矫正' : (molecule.name || molecule.mol_id)

  const handleCorrectionComplete = async (
    results: Array<{ id: string; finalSmiles: string; status: 'confirmed' | 'rejected' | 'corrected' }>,
  ) => {
    if (!libraryRoot) {
      showToast('未指定项目根目录，无法保存', 'error')
      return
    }
    const updates = results
      .filter((r) => r.id === molecule.mol_id)
      .map((r) => ({
        ...molecule,
        esmiles: r.finalSmiles,
        status: r.status,
      }))
    if (updates.length === 0) {
      onSaved?.()
      onClose()
      return
    }
    try {
      const settled = await Promise.allSettled(
        updates.map((record) => molAdminUpdate(libraryRoot, record)),
      )
      const failures = settled.filter(
        (s) => s.status === 'rejected' || (s.status === 'fulfilled' && !s.value),
      )
      if (failures.length > 0) {
        showToast(`保存失败：${failures.length} 条记录未更新`, 'error')
      } else {
        showToast('矫正结果已保存', 'success')
      }
      onSaved?.()
      onClose()
    } catch (e) {
      showToast(e instanceof Error ? e.message : '保存矫正结果失败', 'error')
    }
  }

  return (
    <>
      <div
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0, 0, 0, 0.35)',
          zIndex: 40,
        }}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: '480px',
          maxWidth: '90vw',
          background: 'var(--bg-surface)',
          borderLeft: '1px solid var(--border)',
          zIndex: 50,
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '-4px 0 24px rgba(0, 0, 0, 0.15)',
        }}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 16px',
            borderBottom: '1px solid var(--border)',
          }}
        >
          <h3
            style={{
              margin: 0,
              fontSize: 15,
              fontWeight: 600,
              color: 'var(--text-primary)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={title}
          >
            {title}
          </h3>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            icon={<CloseIcon size={18} />}
            aria-label="关闭"
          />
        </div>

        <div
          style={{
            flex: 1,
            overflow: 'auto',
            padding: '16px',
          }}
        >
          {isCorrectionMode ? (
            <CorrectionPanel
              items={[buildCorrectionItem(molecule)]}
              onComplete={handleCorrectionComplete}
              showSourceImage
            />
          ) : (
            <MoleculeDetailPanel
              molecule={molecule}
              libraryRoot={libraryRoot}
              onSaved={onSaved}
            />
          )}
        </div>
      </div>
    </>
  )
}
