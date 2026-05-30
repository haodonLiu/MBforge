import type { ReactNode } from 'react'

export type BadgeVariant = 'neutral' | 'success' | 'warning' | 'danger'

interface Props {
  children: ReactNode
  variant?: BadgeVariant
  style?: React.CSSProperties
  className?: string
}

const variantMap: Record<BadgeVariant, { color: string; bg: string }> = {
  neutral: { color: 'var(--text-muted)', bg: 'var(--bg-base)' },
  success: { color: '#16a34a', bg: 'rgba(22,163,74,0.1)' },
  warning: { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
  danger:  { color: '#dc2626', bg: 'rgba(220,38,38,0.1)' },
}

export default function Badge({ children, variant = 'neutral', style, className }: Props) {
  const v = variantMap[variant]
  return (
    <span
      className={className}
      style={{
        display: 'inline-block',
        fontSize: '12px',
        color: v.color,
        padding: '2px 8px',
        background: v.bg,
        borderRadius: '4px',
        fontWeight: 500,
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {children}
    </span>
  )
}
