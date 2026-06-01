import type { ReactNode } from 'react'

export interface SectionHeaderProps {
  title: ReactNode
  action?: ReactNode
  style?: React.CSSProperties
  className?: string
}

export default function SectionHeader({ title, action, style, className }: SectionHeaderProps) {
  return (
    <div
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '12px',
        ...style,
      }}
    >
      {typeof title === 'string' ? <SectionTitle>{title}</SectionTitle> : title}
      {action}
    </div>
  )
}

import SectionTitle from './SectionTitle'
