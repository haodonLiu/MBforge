import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  minWidth?: number
  gap?: number
  style?: React.CSSProperties
  className?: string
}

export default function CardGrid({ children, minWidth = 280, gap = 16, style, className }: Props) {
  return (
    <div
      className={className}
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(auto-fill, minmax(${minWidth}px, 1fr))`,
        gap,
        ...style,
      }}
    >
      {children}
    </div>
  )
}
