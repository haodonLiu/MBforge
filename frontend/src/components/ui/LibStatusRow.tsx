import { CheckIcon, XIcon } from '../icons'

export interface LibStatusRowProps {
  name: string
  version?: string | null
  available: boolean
  hint?: string
  showBorder?: boolean
}

export default function LibStatusRow({ name, version, available, hint, showBorder = true }: LibStatusRowProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '6px 0',
        borderBottom: showBorder ? '1px solid #f0f0f0' : 'none',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontWeight: 500, fontSize: '13px' }}>{name}</span>
        {hint && (
          <span style={{ fontSize: '11px', color: '#999' }}>{hint}</span>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {version && (
          <span style={{ fontSize: '11px', color: '#666' }}>v{version}</span>
        )}
        {available ? (
          <CheckIcon size={14} style={{ color: '#16a34a' }} />
        ) : (
          <XIcon size={14} style={{ color: '#dc2626' }} />
        )}
      </div>
    </div>
  )
}
