import type { ReactNode } from 'react'

export type InlineAlertTone = 'success' | 'warning' | 'danger' | 'info'

export interface InlineAlertProps {
  tone: InlineAlertTone
  title?: string
  children?: ReactNode
  className?: string
  style?: React.CSSProperties
}

const toneMap: Record<InlineAlertTone, { border: string; bg: string; color: string }> = {
  success: {
    border: 'var(--success)',
    bg: 'rgba(22, 163, 74, 0.08)',
    color: 'var(--success)',
  },
  warning: {
    border: 'var(--warning)',
    bg: 'rgba(245, 158, 11, 0.08)',
    color: 'var(--warning)',
  },
  danger: {
    border: 'var(--danger)',
    bg: 'rgba(220, 38, 38, 0.08)',
    color: 'var(--danger)',
  },
  info: {
    border: 'var(--accent)',
    bg: 'var(--accent-muted)',
    color: 'var(--accent)',
  },
}

export default function InlineAlert({ tone, title, children, className, style }: InlineAlertProps) {
  const { border, bg, color } = toneMap[tone]
  return (
    <div
      className={className}
      style={{
        padding: '10px 12px',
        borderRadius: 'var(--radius-md)',
        background: bg,
        borderLeft: `3px solid ${border}`,
        color,
        fontSize: '12px',
        lineHeight: '16px',
        ...style,
      }}
    >
      {title && <div style={{ fontWeight: 600, marginBottom: children ? 4 : 0 }}>{title}</div>}
      {children}
    </div>
  )
}
