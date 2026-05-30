import { motion } from 'framer-motion'
import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  delay?: number
  duration?: number
  y?: number
  x?: number
  className?: string
}

export default function FadeIn({
  children,
  delay = 0,
  duration = 0.35,
  y = 8,
  x = 0,
  className,
}: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y, x }}
      animate={{ opacity: 1, y: 0, x: 0 }}
      transition={{ duration, delay, ease: 'easeOut' }}
      className={className}
    >
      {children}
    </motion.div>
  )
}
