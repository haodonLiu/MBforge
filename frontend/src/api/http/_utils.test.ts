import { describe, it, expect, vi } from 'vitest'
import { httpFetch, ErrorCode, AppError } from './_utils'

declare const global: typeof globalThis
describe('httpFetch Pydantic 422 handling', () => {
  it('throws ApiError with joined detail messages for Pydantic validation errors', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      text: async () =>
        JSON.stringify({
          detail: [
            { loc: ['body', 'title'], msg: 'field required', type: 'missing' },
            { loc: ['body', 'page'], msg: 'value is not a valid integer', type: 'type_error' },
          ],
        }),
    } as Response)

    await expect(httpFetch('/api/v1/test', { method: 'POST', body: '{}' })).rejects.toThrow(
      AppError,
    )
    await expect(httpFetch('/api/v1/test', { method: 'POST', body: '{}' })).rejects.toSatisfy(
      (err: AppError) =>
        err.errorCode === ErrorCode.ApiError &&
        err.message.includes('body.title: field required') &&
        err.message.includes('body.page: value is not a valid integer'),
    )
  })

  it('preserves MBForgeError handling for custom 422', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      text: async () =>
        JSON.stringify({
          error: 'invalid root',
          error_code: 'validation_error',
          severity: 'warning',
        }),
    } as Response)

    await expect(httpFetch('/api/v1/test')).rejects.toSatisfy(
      (err: AppError) =>
        err.errorCode === ErrorCode.ApiError && err.message === 'invalid root',
    )
  })
})
