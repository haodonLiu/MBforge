import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  style?: React.CSSProperties
  className?: string
}

export default function SectionTitle({ children, style, className }: Props) {
  return (
    <h2
      className={className}
      style={{
        fontSize: '14px',
        fontWeight: 600,
        color: 'var(--text-secondary)',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        margin: 0,
        ...style,
      }}
    >
      {children}
    </h2>
  )
}
