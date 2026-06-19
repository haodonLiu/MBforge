import type { ReactNode } from 'react'
import { TONE_COLORS } from '../../styles/tokens'

export type InlineAlertTone = 'success' | 'warning' | 'danger' | 'info'

export interface InlineAlertProps {
  tone: InlineAlertTone
  title?: string
  children?: ReactNode
  className?: string
  style?: React.CSSProperties
}

export default function InlineAlert({ tone, title, children, className, style }: InlineAlertProps) {
  const isInfo = tone === 'info'
  const color = isInfo ? 'var(--accent)' : TONE_COLORS[tone].color
  const bg = isInfo ? 'var(--accent-muted)' : TONE_COLORS[tone].bg
  const border = color

  return (
    <div
      className={className}
      style={{
        padding: 'var(--space-2) var(--space-3)',
        borderRadius: 'var(--radius-md)',
        background: bg,
        borderLeft: `3px solid ${border}`,
        color,
        fontSize: 'var(--font-size-small)',
        lineHeight: '16px',
        ...style,
      }}
    >
      {title && <div style={{ fontWeight: 600, marginBottom: children ? 4 : 0 }}>{title}</div>}
      {children}
    </div>
  )
}
