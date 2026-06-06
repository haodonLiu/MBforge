import { motion } from 'framer-motion'
import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
}

export default function AnimatedPage({ children }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -8 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'auto', minHeight: 0 }}
    >
      {children}
    </motion.div>
  )
}
