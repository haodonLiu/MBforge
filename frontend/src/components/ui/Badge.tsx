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

export default function Badge({
  children,
  tone,
  size = 'sm',
  variant,
  dot = false,
  className,
  style,
}: BadgeProps) {
  // Prefer explicit tone; fall back to legacy variant.
  const effectiveVariant: BadgeVariant = tone ? (toneToVariant[tone] ?? 'neutral') : (variant ?? 'neutral')
  const v = TONE_COLORS[effectiveVariant]

  const sizeStyles: Record<'sm' | 'md', React.CSSProperties> = {
    sm: { padding: '2px 8px', fontSize: '11px', gap: dot ? 4 : 0 },
    md: { padding: '4px 10px', fontSize: '12px', gap: dot ? 6 : 4 },
  }

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
        color: v.color,
        background: v.bg,
        ...sizeStyles[size],
        ...style,
      }}
    >
      {dot && (
        <span style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: v.color,
          flexShrink: 0,
        }} />
      )}
      {children}
    </span>
  )
}
