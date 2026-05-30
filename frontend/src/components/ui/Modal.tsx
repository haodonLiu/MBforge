import { motion, AnimatePresence } from 'framer-motion'
import type { ReactNode } from 'react'
import IconButton from './IconButton'
import { XIcon } from '../icons'

interface Props {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
  footer?: ReactNode
  width?: string | number
  maxWidth?: string | number
  height?: string | number
  maxHeight?: string | number
}

export default function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  width = '90%',
  maxWidth = 860,
  height = '80%',
  maxHeight = 640,
}: Props) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {/* Backdrop */}
          <motion.div
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{
              position: 'absolute',
              inset: 0,
              background: 'rgba(0, 0, 0, 0.5)',
              backdropFilter: 'blur(4px)',
            }}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            style={{
              position: 'relative',
              width,
              maxWidth,
              height,
              maxHeight,
              background: 'var(--bg-surface)',
              borderRadius: '16px',
              border: '1px solid var(--border)',
              boxShadow: '0 20px 60px rgba(0, 0, 0, 0.3)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            {/* Header */}
            {title && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '16px 20px',
                borderBottom: '1px solid var(--border)',
                flexShrink: 0,
              }}>
                <h2 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>{title}</h2>
                <IconButton size={32} onClick={onClose} title="关闭">
                  <XIcon size={18} />
                </IconButton>
              </div>
            )}

            {/* Content */}
            <div style={{ flex: 1, overflow: 'auto', padding: '16px 20px' }}>
              {children}
            </div>

            {/* Footer */}
            {footer && (
              <div style={{
                display: 'flex',
                justifyContent: 'flex-end',
                gap: '8px',
                padding: '12px 20px',
                borderTop: '1px solid var(--border)',
                flexShrink: 0,
              }}>
                {footer}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
