import type { ReactNode } from 'react'

export type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'loading'

export interface BadgeProps {
  tone: BadgeTone
  children: ReactNode
  size?: 'sm' | 'md'
  className?: string
  style?: React.CSSProperties
}

const toneStyles: Record<BadgeTone, React.CSSProperties> = {
  success: {
    background: 'rgba(22, 163, 74, 0.10)',
    color: 'var(--success)',
  },
  warning: {
    background: 'rgba(245, 158, 11, 0.10)',
    color: 'var(--warning)',
  },
  danger: {
    background: 'rgba(220, 38, 38, 0.10)',
    color: 'var(--danger)',
  },
  info: {
    background: 'var(--accent-muted)',
    color: 'var(--accent)',
  },
  neutral: {
    background: 'var(--bg-hover)',
    color: 'var(--text-secondary)',
  },
  loading: {
    background: 'var(--bg-hover)',
    color: 'var(--text-secondary)',
  },
}

const sizeStyles: Record<'sm' | 'md', React.CSSProperties> = {
  sm: { padding: '2px 8px', fontSize: '11px', gap: 4 },
  md: { padding: '4px 10px', fontSize: '12px', gap: 6 },
}

export default function Badge({ tone, children, size = 'sm', className, style }: BadgeProps) {
  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        borderRadius: 'var(--radius-md)',
        fontWeight: 500,
        lineHeight: 1,
        whiteSpace: 'nowrap',
        ...toneStyles[tone],
        ...sizeStyles[size],
        ...style,
      }}
    >
      {children}
    </span>
  )
}
