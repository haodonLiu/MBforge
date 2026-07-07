import { useTranslation } from 'react-i18next'
import { CheckIcon, XIcon } from '@/components/icons'
import SectionTitle from '@/components/ui/SectionTitle'

// 库展示元数据 (label + hint 为 i18n key)
export const LIBRARY_INFO: Record<string, { name: string; hint?: string }> = {
  rdkit:    { name: 'RDKit', hint: 'cheminformatics' },
  numpy:    { name: 'NumPy', hint: 'numerical computing' },
  scipy:    { name: 'SciPy', hint: 'scientific computing' },
  pandas:   { name: 'Pandas', hint: 'data analysis' },
  openmm:   { name: 'OpenMM', hint: 'molecular dynamics' },
  vina:     { name: 'AutoDock Vina', hint: 'molecular docking' },
  deepchem: { name: 'DeepChem', hint: 'ADMET prediction' },
  torch:    { name: 'PyTorch', hint: 'deep learning' },
}

// 与后端 /api/v1/environment/check 返回的 capabilities 元素对齐
export interface CapabilityStatus {
  name: string
  available: boolean
  version: string | null
  description: string
  category: string
}

// ============================================================================
// LibRow — 单个库的状态行
// ============================================================================

export function LibRow({ lib }: { lib: CapabilityStatus }) {
  const { t } = useTranslation()
  const info = LIBRARY_INFO[lib.name] || { name: lib.name }
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        background: 'var(--bg-base)',
        borderRadius: '8px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div
          style={{
            width: '24px',
            height: '24px',
            borderRadius: '50%',
            background: lib.available ? 'var(--success)' : 'var(--danger)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            flexShrink: 0,
          }}
        >
          {lib.available ? <CheckIcon size={12} /> : <XIcon size={12} />}
        </div>
        <div>
          <div style={{ fontSize: '14px', fontWeight: 500 }}>{info.name}</div>
          {info.hint && (
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{t(info.hint)}</div>
          )}
        </div>
      </div>
      <div
        style={{
          fontSize: '13px',
          color: lib.available ? 'var(--success)' : 'var(--text-muted)',
        }}
      >
        {lib.available ? lib.version || t('libraries.installed') : t('libraries.notInstalled')}
      </div>
    </div>
  )
}

// ============================================================================
// LibrarySection — 一组库的分类区块
// ============================================================================

export interface LibrarySectionProps {
  title: string
  libs: CapabilityStatus[]
}

export default function LibrarySection({ title, libs }: LibrarySectionProps) {
  return (
    <div
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '16px 20px',
      }}
    >
      <SectionTitle style={{ marginBottom: '12px' }}>
        {title}
      </SectionTitle>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {libs.map(lib => (
          <LibRow key={lib.name} lib={lib} />
        ))}
      </div>
    </div>
  )
}
