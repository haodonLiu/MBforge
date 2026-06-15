import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { invokeWithError, isTauriAvailable, registerGlobalErrorHandlers } from '../_utils'
import { AppError, ErrorCode } from '@/utils/errors'

describe('invokeWithError', () => {
  it('returns resolved value on success', async () => {
    const result = await invokeWithError(() => Promise.resolve('ok'))

    expect(result).toBe('ok')
  })

  it('throws AppError on rejection with original message', async () => {
    await expect(invokeWithError(() => Promise.reject(new Error('boom'))))
      .rejects
      .toBeInstanceOf(AppError)

    await expect(invokeWithError(() => Promise.reject(new Error('boom'))))
      .rejects
      .toMatchObject({ message: 'boom' })
  })

  it('uses default fallback error code TauriInvoke when no fallback provided', async () => {
    await expect(invokeWithError(() => Promise.reject(new Error('boom'))))
      .rejects
      .toMatchObject({ errorCode: ErrorCode.TauriInvoke, message: 'boom' })
  })

  it('wraps non-AppError with the fallback error code', async () => {
    await expect(invokeWithError(() => Promise.reject(new Error('boom')), ErrorCode.Network))
      .rejects
      .toMatchObject({ errorCode: ErrorCode.Network, message: 'boom' })
  })

  it('re-throws AppError without re-wrapping', async () => {
    const original = new AppError(ErrorCode.PdfParse, 'parse failed')

    await expect(invokeWithError(() => Promise.reject(original)))
      .rejects
      .toBe(original)
  })

  it.each([
    { label: 'string', value: 'plain string error' },
    { label: 'null', value: null },
    { label: 'object', value: { reason: 'structured failure' } },
    { label: 'undefined', value: undefined },
  ])('wraps $label rejection value as AppError', async ({ value }) => {
    await expect(invokeWithError(() => Promise.reject(value), ErrorCode.ApiError))
      .rejects
      .toMatchObject({ errorCode: ErrorCode.ApiError, message: String(value) })
  })
})

describe('isTauriAvailable', () => {
  let originalTauri: unknown
  let originalTauriInternals: unknown

  beforeEach(() => {
    originalTauri = (window as any).__TAURI__
    originalTauriInternals = (window as any).__TAURI_INTERNALS__
    delete (window as any).__TAURI__
    delete (window as any).__TAURI_INTERNALS__
  })

  afterEach(() => {
    ;(window as any).__TAURI__ = originalTauri
    ;(window as any).__TAURI_INTERNALS__ = originalTauriInternals
  })

  it('returns false when neither __TAURI__ nor __TAURI_INTERNALS__ is present', () => {
    expect(isTauriAvailable()).toBe(false)
  })
})

describe('registerGlobalErrorHandlers', () => {
  it('attaches error and unhandledrejection listeners and returns a cleanup function', () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const removeSpy = vi.spyOn(window, 'removeEventListener')

    const cleanup = registerGlobalErrorHandlers()

    expect(addSpy).toHaveBeenCalledWith('error', expect.any(Function))
    expect(addSpy).toHaveBeenCalledWith('unhandledrejection', expect.any(Function))

    cleanup()

    expect(removeSpy).toHaveBeenCalledWith('error', expect.any(Function))
    expect(removeSpy).toHaveBeenCalledWith('unhandledrejection', expect.any(Function))

    addSpy.mockRestore()
    removeSpy.mockRestore()
  })
})
