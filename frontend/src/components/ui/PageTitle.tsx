import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  style?: React.CSSProperties
  className?: string
}

export default function PageTitle({ children, style, className }: Props) {
  return (
    <h1
      className={className}
      style={{
        fontSize: 'var(--font-size-title)',
        fontWeight: 600,
        marginBottom: '8px',
        ...style,
      }}
    >
      {children}
    </h1>
  )
}
