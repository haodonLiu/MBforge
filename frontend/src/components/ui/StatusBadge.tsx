import type { ReactNode } from 'react'

export type StatusType = 'ready' | 'pending' | 'error' | 'warning'

export interface StatusBadgeProps {
  type: StatusType
  children: ReactNode
  size?: 'sm' | 'md'
  style?: React.CSSProperties
}

const config: Record<StatusType, { bg: string; color: string; dot: string }> = {
  ready:   { bg: '#dcfce7', color: '#16a34a', dot: '#16a34a' },
  pending: { bg: '#f5f5f5', color: '#666', dot: '#999' },
  warning: { bg: '#fef3c7', color: '#92400e', dot: '#f59e0b' },
  error:   { bg: '#fee2e2', color: '#dc2626', dot: '#dc2626' },
}

export default function StatusBadge({ type, children, size = 'md', style }: StatusBadgeProps) {
  const c = config[type]
  const isSm = size === 'sm'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: isSm ? '4px' : '6px',
        padding: isSm ? '2px 8px' : '4px 10px',
        background: c.bg,
        color: c.color,
        borderRadius: '12px',
        fontSize: isSm ? '11px' : '12px',
        fontWeight: 500,
        ...style,
      }}
    >
      <span style={{
        width: isSm ? '5px' : '6px',
        height: isSm ? '5px' : '6px',
        borderRadius: '50%',
        background: c.dot,
      }} />
      {children}
    </span>
  )
}
