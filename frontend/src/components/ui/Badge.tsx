import type { ReactNode } from 'react'
import { TONE_COLORS } from '../../styles/tokens'

export type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'loading'
export type BadgeVariant = 'neutral' | 'success' | 'warning' | 'danger' | 'info'

export interface BadgeProps {
  children: ReactNode
  /** New API: semantic tone used by the UI upgrade. */
  tone?: BadgeTone
  /** New API: size. */
  size?: 'sm' | 'md'
  /** Legacy API: variant alias for tone. Prefer `tone`. */
  variant?: BadgeVariant
  /** Legacy API: show a left dot. */
  dot?: boolean
  className?: string
  style?: React.CSSProperties
}

const toneToVariant: Record<BadgeTone, BadgeVariant | null> = {
  success: 'success',
  warning: 'warning',
  danger: 'danger',
  info: 'info',
  neutral: 'neutral',
  loading: 'neutral',
}

const toneVarStyles: Record<BadgeTone, React.CSSProperties> = {
  success: { background: 'var(--success)', color: '#fff' },
  warning: { background: 'var(--warning)', color: '#fff' },
  danger:  { background: 'var(--danger)',  color: '#fff' },
  info:    { background: 'var(--accent)',  color: '#fff' },
  neutral: { background: 'var(--bg-hover)', color: 'var(--text-secondary)' },
  loading: { background: 'var(--bg-hover)', color: 'var(--text-secondary)' },
}

const sizeStyles: Record<'sm' | 'md', React.CSSProperties> = {
  sm: { padding: '2px 8px', fontSize: '11px' },
  md: { padding: '4px 10px', fontSize: '12px' },
}

export default function Badge({
  children,
  tone,
  size = 'sm',
  variant,
  dot = false,
  className,
  style,
}: BadgeProps) {
  // New `tone` API uses CSS variables; legacy `variant`/`dot` API stays on TONE_COLORS.
  const toneColors = tone ? toneVarStyles[tone] : null
  const legacyColors = TONE_COLORS[tone ? (toneToVariant[tone] ?? 'neutral') : (variant ?? 'neutral')]

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
        color: toneColors ? toneColors.color : legacyColors.color,
        background: toneColors ? toneColors.background : legacyColors.bg,
        gap: dot ? (size === 'sm' ? 4 : 6) : 0,
        ...sizeStyles[size],
        ...style,
      }}
    >
      {dot && (
        <span style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: toneColors ? toneColors.color : legacyColors.color,
          flexShrink: 0,
        }} />
      )}
      {children}
    </span>
  )
}
