/** HTTP communication layer for web mode. */

const API_BASE = 'http://127.0.0.1:18792'

export { AppError, ErrorCode, getErrorMessage } from '@/utils/errors'
import { AppError, ErrorCode, getErrorMessage } from '@/utils/errors'
import { showToast } from '@/hooks/useToast'

const NETWORK_KEYWORDS = ['network', 'connection', 'timeout', 'refused'] as const

function classifyError(err: unknown): { code: ErrorCode; message: string } {
  if (err instanceof AppError) return { code: err.errorCode, message: err.message }
  const raw = err instanceof Error ? err.message : String(err)
  const lower = raw.toLowerCase()
  if (NETWORK_KEYWORDS.some(k => lower.includes(k))) return { code: ErrorCode.Network, message: getErrorMessage(ErrorCode.Network) }
  return { code: ErrorCode.Unknown, message: raw }
}

export async function httpFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`
  try {
    const resp = await fetch(url, { headers: { 'Content-Type': 'application/json', ...options.headers }, ...options })
    if (!resp.ok) {
      const body = await resp.text().catch(() => '')
      throw new AppError(ErrorCode.Network, `HTTP ${resp.status}: ${body.slice(0, 200)}`)
    }
    return await resp.json()
  } catch (err) {
    if (err instanceof AppError) throw err
    const c = classifyError(err)
    throw new AppError(c.code, c.message)
  }
}

export async function httpPost<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  return httpFetch<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

export async function httpGet<T>(path: string): Promise<T> {
  return httpFetch<T>(path, { method: 'GET' })
}

export async function httpPut<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  return httpFetch<T>(path, { method: 'PUT', body: JSON.stringify(body) })
}

export async function httpDelete<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  return httpFetch<T>(path, { method: 'DELETE', ...(body ? { body: JSON.stringify(body) } : {}) })
}

export async function invokeWithError<T>(fn: () => Promise<T>, fallbackCode: ErrorCode = ErrorCode.Unknown): Promise<T> {
  try { return await fn() }
  catch (err) {
    const appErr = err instanceof AppError ? err : new AppError(fallbackCode, err instanceof Error ? err.message : String(err))
    console.error(`[invokeWithError] ${appErr.errorCode}: ${appErr.message}`)
    throw appErr
  }
}

export function registerGlobalErrorHandlers(): () => void {
  if (typeof window === 'undefined') return () => {}
  const onError = (event: ErrorEvent) => { const c = classifyError(event.error ?? event.message); showToast(`未捕获的错误: ${c.message}`, 'error') }
  const onRejection = (event: PromiseRejectionEvent) => { const c = classifyError(event.reason); showToast(`未处理的 Promise 异常: ${c.message}`, 'error') }
  window.addEventListener('error', onError)
  window.addEventListener('unhandledrejection', onRejection)
  return () => { window.removeEventListener('error', onError); window.removeEventListener('unhandledrejection', onRejection) }
}

export async function openExternalUrl(url: string): Promise<void> {
  if (!url || (!url.startsWith('http://') && !url.startsWith('https://'))) { showToast(`无效的链接: ${url}`, 'error'); return }
  window.open(url, '_blank', 'noopener,noreferrer')
}
