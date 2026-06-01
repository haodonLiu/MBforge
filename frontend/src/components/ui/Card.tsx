import { motion } from 'framer-motion'
import type { ReactNode, MouseEvent } from 'react'

export interface CardProps {
  children: ReactNode
  padding?: number | string
  hoverable?: boolean
  onClick?: (e: MouseEvent<HTMLDivElement>) => void
  style?: React.CSSProperties
  className?: string
}

export default function Card({ children, padding = '20px', hoverable = false, onClick, style, className }: CardProps) {
  const baseStyle: React.CSSProperties = {
    padding,
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: '12px',
    cursor: onClick ? 'pointer' : (hoverable ? 'pointer' : undefined),
    transition: 'all 0.15s',
    ...style,
  }

  if (hoverable || onClick) {
    return (
      <motion.div
        className={className}
        onClick={onClick}
        style={baseStyle}
        whileHover={{ scale: 1.01, boxShadow: '0 4px 16px rgba(0,0,0,0.06)' }}
        transition={{ duration: 0.15 }}
      >
        {children}
      </motion.div>
    )
  }

  return (
    <div className={className} style={baseStyle}>
      {children}
    </div>
  )
}
