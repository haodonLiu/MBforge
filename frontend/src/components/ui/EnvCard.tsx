import type { ReactNode } from 'react'

interface Props {
  label: string
  value: string | ReactNode
  subValue?: string
  variant?: 'default' | 'success' | 'warning' | 'error'
  style?: React.CSSProperties
}

const variantStyles = {
  default: { bg: '#f5f5f5', color: 'inherit' },
  success: { bg: '#dcfce7', color: '#16a34a' },
  warning: { bg: '#fef3c7', color: '#92400e' },
  error:   { bg: '#fee2e2', color: '#dc2626' },
}

export default function EnvCard({ label, value, subValue, variant = 'default', style }: Props) {
  const v = variantStyles[variant]

  return (
    <div
      style={{
        padding: '10px 14px',
        background: v.bg,
        borderRadius: '8px',
        fontSize: '13px',
        color: v.color,
        ...style,
      }}
    >
      <span style={{ color: '#666', marginRight: '6px' }}>{label}</span>
      <strong style={{ fontWeight: 600 }}>{value}</strong>
      {subValue && (
        <span style={{ color: '#999', marginLeft: '4px', fontSize: '12px' }}>{subValue}</span>
      )}
    </div>
  )
}
