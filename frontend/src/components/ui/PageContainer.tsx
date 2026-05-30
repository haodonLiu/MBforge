import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  noPadding?: boolean
  style?: React.CSSProperties
  className?: string
}

export default function PageContainer({ children, noPadding = false, style, className }: Props) {
  return (
    <div
      className={className}
      style={{
        flex: 1,
        padding: noPadding ? 0 : '32px',
        overflow: 'auto',
        display: 'flex',
        flexDirection: 'column',
        ...style,
      }}
    >
      {children}
    </div>
  )
}
