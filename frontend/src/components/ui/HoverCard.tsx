import { motion } from 'framer-motion'
import type { ReactNode, MouseEvent } from 'react'

interface Props {
  children: ReactNode
  onClick?: (e: MouseEvent<HTMLDivElement>) => void
  style?: React.CSSProperties
  className?: string
}

export default function HoverCard({ children, onClick, style, className }: Props) {
  return (
    <motion.div
      className={className}
      onClick={onClick}
      style={{
        padding: '20px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        cursor: onClick ? 'pointer' : undefined,
        ...style,
      }}
      whileHover={{ scale: 1.01, boxShadow: '0 4px 16px rgba(0,0,0,0.06)' }}
      transition={{ duration: 0.15 }}
    >
      {children}
    </motion.div>
  )
}
