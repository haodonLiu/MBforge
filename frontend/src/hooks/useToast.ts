import { useState, useCallback, useRef } from 'react'

export type ToastType = 'success' | 'error' | 'info'

export interface ToastItem {
  id: string
  message: string
  type: ToastType
}

let globalToasts: ToastItem[] = []
let listeners: (() => void)[] = []

function notify() {
  listeners.forEach((l) => l())
}

export function showToast(message: string, type: ToastType = 'info') {
  const id = crypto.randomUUID()
  globalToasts = [...globalToasts, { id, message, type }]
  notify()
  setTimeout(() => {
    globalToasts = globalToasts.filter((t) => t.id !== id)
    notify()
  }, 3000)
}

export function useToast() {
  const [, setTick] = useState(0)
  const toastsRef = useRef(globalToasts)

  const refresh = useCallback(() => {
    toastsRef.current = globalToasts
    setTick((t) => t + 1)
  }, [])

  useState(() => {
    listeners.push(refresh)
    return () => {
      listeners = listeners.filter((l) => l !== refresh)
    }
  })

  return { toasts: toastsRef.current }
}
