/** HTTP communication layer for web mode. */

import {
  AppError,
  ErrorCode,
  Severity,
  getErrorMessage,
  severityFromHttpStatus,
  type AppErrorOpts,
} from '@/utils/errors'
export { AppError, ErrorCode, getErrorMessage, Severity } from '@/utils/errors'
import { showToast } from '@/hooks/useToast'

const API_BASE = ''

const NETWORK_KEYWORDS = ['network', 'connection', 'timeout', 'refused'] as const

/**
 * Coerce arbitrary case `severity` strings from the backend JSON into the
 * canonical `Severity` enum value. Unknown values fall through as `undefined`,
 * which lets the caller fall back to status-derived severity.
 */
function normalizeSeverity(raw: unknown): Severity | undefined {
  if (typeof raw !== 'string') return undefined
  const upper = raw.toUpperCase()
  if (upper === 'DEBUG' || upper === 'INFO' || upper === 'WARNING' || upper === 'ERROR' || upper === 'FATAL') {
    return upper as Severity
  }
  return undefined
}

function classifyError(err: unknown): { code: ErrorCode; message: string } {
  if (err instanceof AppError) return { code: err.errorCode, message: err.message }
  const raw = err instanceof Error ? err.message : String(err)
  const lower = raw.toLowerCase()
  if (NETWORK_KEYWORDS.some(k => lower.includes(k))) {
    return { code: ErrorCode.Network, message: getErrorMessage(ErrorCode.Network) }
  }
  return { code: ErrorCode.Unknown, message: raw }
}

/**
 * Map a backend `error_code` string to the closest `ErrorCode` enum value.
 * Falls back to `Network` when the server reports a code we don't recognize
 * — the body still carries the *real* `error_code` in `context.backend_code`,
 * so operators retain visibility without forcing every backend code into TS.
 */
function backendCodeToErrorCode(backendCode?: string): ErrorCode {
  if (!backendCode) return ErrorCode.Network
  switch (backendCode) {
    case 'unknown':
      return ErrorCode.Unknown
    case 'model_not_available':
      return ErrorCode.ModelNotAvailable
    case 'pdf_parse_error':
      return ErrorCode.PdfParse
    case 'project_not_valid':
    case 'project_open':
      return ErrorCode.ProjectOpen
    case 'settings_error':
      return ErrorCode.SettingsLoad
    case 'molecule_search':
      return ErrorCode.MoleculeSearch
    case 'validation_error':
    case 'config_error':
    case 'file_access_error':
    case 'path_traversal':
      return ErrorCode.ApiError
    default:
      return ErrorCode.Network
  }
}

export async function httpFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`
  try {
    const resp = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    })
    if (!resp.ok) {
      const body = await resp.text().catch(() => '')
      let payload: Record<string, unknown> | null = null
      try {
        payload = body ? JSON.parse(body) : null
      } catch {
        // Non-JSON body — fall through to legacy fallback.
      }

      // Pydantic ValidationError shape: { detail: [{loc, msg, type}, ...] }
      if (
        resp.status === 422 &&
        payload &&
        Array.isArray(payload.detail)
      ) {
        const detail = payload.detail as Array<{ loc?: string[]; msg?: string }>
        const msg = detail
          .map((e) => `${(e.loc ?? []).join('.')}: ${e.msg ?? 'invalid'}`)
          .join('; ')
        throw new AppError(ErrorCode.ApiError, msg || 'Validation failed', {
          severity: severityFromHttpStatus(resp.status),
          context: { http_status: resp.status, backend_code: 'validation_error' },
        })
      }

      const code = payload
        ? backendCodeToErrorCode(payload.error_code as string | undefined)
        : ErrorCode.Network
      const message = payload?.error
        ? String(payload.error)
        : `HTTP ${resp.status}: ${body.slice(0, 200)}`
      const opts: AppErrorOpts = {
        severity: normalizeSeverity(payload?.severity) ?? severityFromHttpStatus(resp.status),
        category: payload?.category as string | undefined,
        context: {
          ...(payload?.context as Record<string, unknown> | undefined),
          http_status: resp.status,
          ...(payload?.error_code
            ? { backend_code: String(payload.error_code) }
            : {}),
        },
        timestamp: payload?.timestamp as number | undefined,
      }
      throw new AppError(code, message, opts)
    }
    return (await resp.json()) as T
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

export async function invokeWithError<T>(
  fn: () => Promise<T>,
  fallbackCode: ErrorCode = ErrorCode.Unknown,
): Promise<T> {
  try {
    return await fn()
  } catch (err) {
    const appErr =
      err instanceof AppError
        ? err
        : new AppError(fallbackCode, err instanceof Error ? err.message : String(err))
    console.error(`[invokeWithError] ${appErr.errorCode}: ${appErr.message}`)
    throw appErr
  }
}

export function registerGlobalErrorHandlers(): () => void {
  if (typeof window === 'undefined') return () => {}
  const onError = (event: ErrorEvent) => {
    const c = classifyError(event.error ?? event.message)
    showToast(`未捕获的错误: ${c.message}`, 'error')
  }
  const onRejection = (event: PromiseRejectionEvent) => {
    const c = classifyError(event.reason)
    showToast(`未处理的 Promise 异常: ${c.message}`, 'error')
  }
  window.addEventListener('error', onError)
  window.addEventListener('unhandledrejection', onRejection)
  return () => {
    window.removeEventListener('error', onError)
    window.removeEventListener('unhandledrejection', onRejection)
  }
}

export async function openExternalUrl(url: string): Promise<void> {
  if (!url || (!url.startsWith('http://') && !url.startsWith('https://'))) {
    showToast(`无效的链接: ${url}`, 'error')
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}
