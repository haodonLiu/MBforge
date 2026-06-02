import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useToast } from '../useToast'

describe('useToast', () => {
  it('returns toast interface', () => {
    const { result } = renderHook(() => useToast())

    expect(result.current).toHaveProperty('toasts')
    expect(result.current).toHaveProperty('show')
    expect(result.current).toHaveProperty('dismiss')
    expect(result.current).toHaveProperty('success')
    expect(result.current).toHaveProperty('error')
    expect(result.current).toHaveProperty('info')
    expect(result.current).toHaveProperty('warning')
    expect(result.current).toHaveProperty('refresh')
  })

  it('has empty toasts by default', () => {
    const { result } = renderHook(() => useToast())

    expect(result.current.toasts).toEqual([])
  })

  it('success is a function', () => {
    const { result } = renderHook(() => useToast())

    expect(typeof result.current.success).toBe('function')
  })

  it('error is a function', () => {
    const { result } = renderHook(() => useToast())

    expect(typeof result.current.error).toBe('function')
  })

  it('refresh is a function', () => {
    const { result } = renderHook(() => useToast())

    expect(typeof result.current.refresh).toBe('function')
  })
})
