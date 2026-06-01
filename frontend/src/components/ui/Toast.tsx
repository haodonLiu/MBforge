import { AnimatePresence, motion } from 'framer-motion'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { CheckIcon, AlertIcon, InfoIcon, XIcon } from '../icons'
import Button from './Button'
import { PALETTE } from '../../styles/tokens'

// ============================================================================
// 类型
// ============================================================================

export type ToastType = 'success' | 'error' | 'info' | 'warning'

export interface ToastItem {
  id: string
  message: string
  type: ToastType
  /** 自动消失毫秒数（0 表示不自动消失）*/
  duration?: number
  /** 操作按钮（如"撤销"）*/
  action?: {
    label: string
    onClick: () => void
  }
  /** 关闭回调 */
  onClose?: () => void
}

// ============================================================================
// 全局 store
// ============================================================================

let globalToasts: ToastItem[] = []
let listeners: (() => void)[] = []

function notify() {
  listeners.forEach(l => l())
}

/**
 * 显示一条 Toast。
 * 向后兼容两种调用方式：
 *   - showToast(message, type, duration?)  — 旧式 (string, 'info')
 *   - showToast({ message, type, action, duration }) — 新式（选项对象）
 */
function showToast(
  messageOrItem: string | Omit<ToastItem, 'id'>,
  typeOrUndefined?: ToastType,
  duration?: number,
): string {
  let item: Omit<ToastItem, 'id'>
  if (typeof messageOrItem === 'string') {
    item = { message: messageOrItem, type: typeOrUndefined ?? 'info' }
    if (duration !== undefined) item.duration = duration
  } else {
    item = messageOrItem
  }
  const id = crypto.randomUUID()
  const newItem: ToastItem = { id, ...item }
  globalToasts = [...globalToasts, newItem]
  notify()
  if (newItem.duration !== 0) {
    setTimeout(() => dismissToast(id), newItem.duration ?? 3000)
  }
  return id
}

export { showToast }

function dismissToast(id: string) {
  const item = globalToasts.find(t => t.id === id)
  if (!item) return
  item.onClose?.()
  globalToasts = globalToasts.filter(t => t.id !== id)
  notify()
}

export { dismissToast }

// 便捷方法
export const toast = {
  success: (message: string, opts?: Partial<ToastItem>) =>
    showToast({ message, type: 'success', ...opts }),
  error: (message: string, opts?: Partial<ToastItem>) =>
    showToast({ message, type: 'error', ...opts }),
  info: (message: string, opts?: Partial<ToastItem>) =>
    showToast({ message, type: 'info', ...opts }),
  warning: (message: string, opts?: Partial<ToastItem>) =>
    showToast({ message, type: 'warning', ...opts }),
}

// ============================================================================
// Hook & Provider
// ============================================================================

interface ToastContextValue {
  toasts: ToastItem[]
  show: typeof showToast
  dismiss: (id: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>(globalToasts)

  useEffect(() => {
    const listener = () => setToasts([...globalToasts])
    listeners.push(listener)
    setToasts([...globalToasts])
    return () => {
      listeners = listeners.filter(l => l !== listener)
    }
  }, [])

  return (
    <ToastContext.Provider value={{ toasts, show: showToast, dismiss: dismissToast }}>
      {children}
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    // 没有 Provider 时 fallback 到全局方法
    return { toasts: globalToasts, show: showToast, dismiss: dismissToast }
  }
  return ctx
}

// ============================================================================
// 渲染组件
// ============================================================================

function toastColor(type: ToastType): string {
  switch (type) {
    case 'success': return PALETTE.success
    case 'error': return PALETTE.danger
    case 'warning': return PALETTE.warning
    default: return PALETTE.info
  }
}

function ToastIcon({ type }: { type: ToastType }) {
  if (type === 'success') return <CheckIcon size={16} />
  if (type === 'error') return <AlertIcon size={16} />
  if (type === 'warning') return <AlertIcon size={16} />
  return <InfoIcon size={16} />
}

export interface ToastContainerProps {
  /** 自定义位置 */
  position?: 'top-right' | 'top-center' | 'top-left' | 'bottom-right' | 'bottom-center' | 'bottom-left'
  /** 最大同时显示数 */
  maxCount?: number
}

const positionStyle: Record<NonNullable<ToastContainerProps['position']>, React.CSSProperties> = {
  'top-right':    { top: 16, right: 16, alignItems: 'flex-end' },
  'top-center':   { top: 16, left: '50%', transform: 'translateX(-50%)', alignItems: 'center' },
  'top-left':     { top: 16, left: 16, alignItems: 'flex-start' },
  'bottom-right': { bottom: 16, right: 16, alignItems: 'flex-end', flexDirection: 'column-reverse' },
  'bottom-center':{ bottom: 16, left: '50%', transform: 'translateX(-50%)', alignItems: 'center', flexDirection: 'column-reverse' },
  'bottom-left':  { bottom: 16, left: 16, alignItems: 'flex-start', flexDirection: 'column-reverse' },
}

export function ToastContainer({ position = 'top-right', maxCount = 5 }: ToastContainerProps = {}) {
  const { toasts, dismiss } = useToast()
  const visible = toasts.slice(-maxCount)

  return (
    <div
      style={{
        position: 'fixed',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        pointerEvents: 'none',
        ...positionStyle[position],
      }}
    >
      <AnimatePresence>
        {visible.map(toastItem => (
          <motion.div
            key={toastItem.id}
            layout
            initial={{ opacity: 0, x: position.includes('right') ? 50 : position.includes('left') ? -50 : 0, y: position.includes('top') ? -20 : 20, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, y: 0, scale: 1 }}
            exit={{ opacity: 0, x: position.includes('right') ? 50 : position.includes('left') ? -50 : 0, scale: 0.9 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            style={{
              pointerEvents: 'auto',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '12px 16px',
              background: 'var(--bg-surface)',
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              boxShadow: '0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)',
              fontSize: 13,
              color: 'var(--text-primary)',
              minWidth: 240,
              maxWidth: 420,
            }}
          >
            <span style={{ color: toastColor(toastItem.type), flexShrink: 0 }}>
              <ToastIcon type={toastItem.type} />
            </span>
            <span style={{ flex: 1 }}>{toastItem.message}</span>
            {toastItem.action && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  toastItem.action!.onClick()
                  dismiss(toastItem.id)
                }}
                style={{ flexShrink: 0, padding: '4px 8px', fontSize: 12 }}
              >
                {toastItem.action.label}
              </Button>
            )}
            <button
              type="button"
              onClick={() => dismiss(toastItem.id)}
              style={{
                background: 'none',
                border: 'none',
                padding: 4,
                cursor: 'pointer',
                color: 'var(--text-muted)',
                display: 'flex',
                alignItems: 'center',
                flexShrink: 0,
              }}
              aria-label="关闭"
            >
              <XIcon size={12} />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}

// 默认导出（向后兼容旧的 ToastContainer 用法）
export default ToastContainer
