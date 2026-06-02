import { CheckIcon, XIcon } from '../icons'

// 库展示元数据 (label + hint)
export const LIBRARY_INFO: Record<string, { name: string; hint?: string }> = {
  rdkit:    { name: 'RDKit', hint: '分子信息学' },
  numpy:    { name: 'NumPy', hint: '数值计算' },
  scipy:    { name: 'SciPy', hint: '科学计算' },
  pandas:   { name: 'Pandas', hint: '数据分析' },
  openmm:   { name: 'OpenMM', hint: '分子动力学' },
  vina:     { name: 'AutoDock Vina', hint: '分子对接' },
  deepchem: { name: 'DeepChem', hint: 'ADMET 预测' },
  torch:    { name: 'PyTorch', hint: '深度学习' },
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
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{info.hint}</div>
          )}
        </div>
      </div>
      <div
        style={{
          fontSize: '13px',
          color: lib.available ? 'var(--success)' : 'var(--text-muted)',
        }}
      >
        {lib.available ? lib.version || 'Installed' : 'Not installed'}
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
        padding: '16px 20px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
      }}
    >
      <div
        style={{
          fontSize: '12px',
          fontWeight: 600,
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          marginBottom: '12px',
        }}
      >
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {libs.map(lib => (
          <LibRow key={lib.name} lib={lib} />
        ))}
      </div>
    </div>
  )
}
