/** Shared utilities for Tauri IPC bridges. */

import { AppError, ErrorCode, getErrorMessage } from '@/utils/errors'
import { showToast } from '@/hooks/useToast'

/** True when running inside a Tauri webview (desktop app). */
export function isTauriAvailable(): boolean {
  try {
    return typeof window !== 'undefined' && (
      typeof (window as any).__TAURI_INTERNALS__ !== 'undefined' ||
      typeof (window as any).__TAURI__ !== 'undefined'
    )
  } catch {
    return false
  }
}

const NETWORK_KEYWORDS = ['network', 'fetch', 'connection', 'timeout', 'refused'] as const

function classifyError(err: unknown): { code: ErrorCode; message: string } {
  const raw = err instanceof Error ? err.message : String(err)
  const lower = raw.toLowerCase()

  if (NETWORK_KEYWORDS.some(keyword => lower.includes(keyword))) {
    return { code: ErrorCode.Network, message: getErrorMessage(ErrorCode.Network) }
  }
  if (lower.includes('permission') || lower.includes('access denied') || lower.includes('not allowed')) {
    return { code: ErrorCode.TauriInvoke, message: '权限不足，请检查文件或系统权限' }
  }
  return { code: ErrorCode.Unknown, message: raw }
}

/**
 * Call a Tauri invoke with structured error handling.
 * Catches invoke errors and wraps them as AppError with a user-friendly message.
 */
export async function invokeWithError<T>(
  fn: () => Promise<T>,
  fallbackCode: ErrorCode = ErrorCode.TauriInvoke,
): Promise<T> {
  try {
    return await fn()
  } catch (err) {
    const appErr = err instanceof AppError
      ? err
      : new AppError(
          fallbackCode,
          err instanceof Error ? err.message : String(err),
        )
    console.error(`[invokeWithError] ${appErr.errorCode}: ${appErr.message}`)
    throw appErr
  }
}

/**
 * Register global error handlers for uncaught errors and promise rejections.
 * Displays toast notifications instead of silently logging to console.
 * Returns a cleanup function.
 */
export function registerGlobalErrorHandlers(): () => void {
  const onError = (event: ErrorEvent) => {
    const classified = classifyError(event.error ?? event.message)
    console.error('[global] Uncaught error:', event.error ?? event.message)
    showToast(`未捕获的错误: ${classified.message}`, 'error')
  }

  const onRejection = (event: PromiseRejectionEvent) => {
    const classified = classifyError(event.reason)
    console.error('[global] Unhandled rejection:', classified.message)
    showToast(`未处理的 Promise 异常: ${classified.message}`, 'error')
  }

  window.addEventListener('error', onError)
  window.addEventListener('unhandledrejection', onRejection)

  return () => {
    window.removeEventListener('error', onError)
    window.removeEventListener('unhandledrejection', onRejection)
  }
}
