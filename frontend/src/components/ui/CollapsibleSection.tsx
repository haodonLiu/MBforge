import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRightIcon } from '../icons'

interface Props {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
  badge?: string | number
  style?: React.CSSProperties
}

export default function CollapsibleSection({ title, children, defaultOpen = true, badge, style }: Props) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div style={style}>
      <div
        onClick={() => setIsOpen(!isOpen)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 0',
          cursor: 'pointer',
          userSelect: 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <motion.div
            animate={{ rotate: isOpen ? 90 : 0 }}
            transition={{ duration: 0.2 }}
          >
            <ChevronRightIcon size={14} style={{ color: '#999' }} />
          </motion.div>
          <span style={{ fontWeight: 600, fontSize: '13px' }}>{title}</span>
          {badge !== undefined && (
            <span style={{
              fontSize: '11px',
              padding: '2px 6px',
              background: '#f0f0f0',
              borderRadius: '10px',
              color: '#666',
            }}>
              {badge}
            </span>
          )}
        </div>
      </div>
      
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
