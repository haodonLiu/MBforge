import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// Mock the Tauri listen API
const mockListen = vi.fn()
vi.mock('@tauri-apps/api/event', () => ({
  listen: (...args: unknown[]) => mockListen(...args),
  emit: vi.fn(),
}))

import { useDocResult } from '../useDocResult'
import { EVT } from '../../api/tauri-events'
import type { DocumentReport } from '../../types'

describe('useDocResult', () => {
  beforeEach(() => {
    mockListen.mockReset()
  })

  it('initializes with empty state', () => {
    mockListen.mockResolvedValue(() => {})
    const { result } = renderHook(() => useDocResult())

    expect(result.current.report).toBeNull()
    expect(result.current.litReviewed).toBe(false)
    expect(result.current.litDecision).toBeNull()
    expect(result.current.lastEventAt).toBeNull()
  })

  it('subscribes to doc-result event on mount', () => {
    mockListen.mockResolvedValue(() => {})
    renderHook(() => useDocResult())

    expect(mockListen).toHaveBeenCalledTimes(1)
    expect(mockListen).toHaveBeenCalledWith(EVT.DocResult, expect.any(Function))
  })

  it('extracts lit_reviewed and lit_decision_summary on event', async () => {
    let capturedHandler: ((event: { payload: DocumentReport }) => void) | null = null
    mockListen.mockImplementation((eventName: string, handler: unknown) => {
      if (eventName === EVT.DocResult) {
        capturedHandler = handler as (event: { payload: DocumentReport }) => void
      }
      return Promise.resolve(() => {})
    })

    const { result } = renderHook(() => useDocResult())

    // Simulate Tauri event
    const report: DocumentReport = {
      metadata: {
        title: 'Test',
        authors: ['Author 1'],
        document_type: 'patent',
        key_targets: ['JAK1'],
        source_file: 'test.pdf',
      },
      compounds: [],
      activities: [],
      key_findings: [],
      sar_analysis: '',
      uncertain_items: [],
      report_markdown: '# Test',
      lit_reviewed: true,
      lit_decision_summary: '3 compounds approved, 1 needs review',
    }

    act(() => {
      capturedHandler!({ payload: report })
    })

    expect(result.current.report).toEqual(report)
    expect(result.current.litReviewed).toBe(true)
    expect(result.current.litDecision).toBe('3 compounds approved, 1 needs review')
    expect(result.current.lastEventAt).not.toBeNull()
  })

  it('handles event without lit_reviewed (default false)', async () => {
    let capturedHandler: ((event: { payload: DocumentReport }) => void) | null = null
    mockListen.mockImplementation((eventName: string, handler: unknown) => {
      if (eventName === EVT.DocResult) {
        capturedHandler = handler as (event: { payload: DocumentReport }) => void
      }
      return Promise.resolve(() => {})
    })

    const { result } = renderHook(() => useDocResult())

    const report: DocumentReport = {
      metadata: {
        title: null,
        authors: [],
        document_type: 'paper',
        key_targets: [],
        source_file: null,
      },
      compounds: [],
      activities: [],
      key_findings: [],
      sar_analysis: '',
      uncertain_items: [],
      report_markdown: '',
      lit_reviewed: false,
      lit_decision_summary: null,
    }

    act(() => {
      capturedHandler!({ payload: report })
    })

    expect(result.current.litReviewed).toBe(false)
    expect(result.current.litDecision).toBeNull()
  })

  it('unsubscribes on unmount', async () => {
    const unlisten = vi.fn()
    let resolveListen: (fn: () => void) => void = () => {}
    mockListen.mockImplementation(() => new Promise((resolve) => {
      resolveListen = resolve
    }))

    const { unmount } = renderHook(() => useDocResult())

    // 等待 listen() 解析 — hook 的 useEffect 是 async
    await act(async () => {
      resolveListen(unlisten)
      await Promise.resolve()
    })

    unmount()

    expect(unlisten).toHaveBeenCalledTimes(1)
  })
})
