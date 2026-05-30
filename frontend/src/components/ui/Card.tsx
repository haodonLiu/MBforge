import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  padding?: number | string
  hoverable?: boolean
  style?: React.CSSProperties
  className?: string
}

export default function Card({ children, padding = '20px', hoverable = false, style, className }: Props) {
  return (
    <div
      className={className}
      style={{
        padding,
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        transition: hoverable ? 'all 0.15s' : undefined,
        cursor: hoverable ? 'pointer' : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  )
}
