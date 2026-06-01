import type { ReactNode } from 'react'
import { TONE_COLORS } from '../../styles/tokens'

export type BadgeVariant = 'neutral' | 'success' | 'warning' | 'danger' | 'info'

export interface BadgeProps {
  children: ReactNode
  variant?: BadgeVariant
  /** 显示左侧小圆点指示器 */
  dot?: boolean
  style?: React.CSSProperties
  className?: string
}

const variantMap: Record<BadgeVariant, keyof typeof TONE_COLORS> = {
  neutral: 'neutral',
  success: 'success',
  warning: 'warning',
  danger:  'danger',
  info:    'info',
}

export default function Badge({ children, variant = 'neutral', dot = false, style, className }: BadgeProps) {
  const v = TONE_COLORS[variantMap[variant]]

  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: dot ? '4px' : 0,
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
