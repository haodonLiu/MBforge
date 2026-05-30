import { AnimatePresence, motion } from 'framer-motion'
import { useToast } from '../hooks/useToast'
import { CheckIcon, AlertIcon, InfoIcon } from './icons'

function ToastIcon({ type }: { type: string }) {
  if (type === 'success') return <CheckIcon size={16} />
  if (type === 'error') return <AlertIcon size={16} />
  return <InfoIcon size={16} />
}

function ToastColor(type: string): string {
  if (type === 'success') return 'var(--success)'
  if (type === 'error') return 'var(--danger)'
  return '#3b82f6'
}

export default function ToastContainer() {
  const { toasts } = useToast()

  return (
    <div
      style={{
        position: 'fixed',
        top: 16,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        pointerEvents: 'none',
      }}
    >
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, y: -20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            style={{
              pointerEvents: 'auto',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '10px 16px',
              background: 'var(--bg-base)',
              border: '1px solid var(--border)',
              borderRadius: 10,
              boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
              fontSize: 13,
              color: 'var(--text-primary)',
              minWidth: 200,
            }}
          >
            <span style={{ color: ToastColor(toast.type), flexShrink: 0 }}>
              <ToastIcon type={toast.type} />
            </span>
            <span>{toast.message}</span>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
