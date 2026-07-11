import { motion, AnimatePresence } from 'framer-motion'
import type { ReactNode } from 'react'
import IconButton from './IconButton'
import ScrollColumn from './ScrollColumn'
import { XIcon } from '../icons'
import { useIsMobile } from '../../styles/responsive'

export interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
  footer?: ReactNode
  width?: string | number
  maxWidth?: string | number
  height?: string | number
  maxHeight?: string | number
  /** 移动端是否全屏显示（默认 true） */
  fullScreenOnMobile?: boolean
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
  fullScreenOnMobile = true,
}: ModalProps) {
  const isMobile = useIsMobile()

  // 移动端可选全屏显示
  const finalWidth = isMobile && fullScreenOnMobile ? '100%' : width
  const finalMaxWidth = isMobile && fullScreenOnMobile ? '100%' : maxWidth
  const finalHeight = isMobile && fullScreenOnMobile ? '100%' : height
  const finalMaxHeight = isMobile && fullScreenOnMobile ? '100%' : maxHeight
  const borderRadius = isMobile && fullScreenOnMobile ? 0 : 16

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
              width: finalWidth,
              maxWidth: finalMaxWidth,
              height: finalHeight,
              maxHeight: finalMaxHeight,
              background: 'var(--bg-surface)',
              borderRadius,
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
                <IconButton size={40} onClick={onClose} title="关闭">
                  <XIcon size={18} />
                </IconButton>
              </div>
            )}

            {/* Content */}
            <ScrollColumn padding="16px 20px">
              {children}
            </ScrollColumn>

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
