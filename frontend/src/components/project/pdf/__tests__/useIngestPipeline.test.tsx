import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useIngestPipeline } from '../useIngestPipeline'
import type { IngestTask } from '@/api/http/ingest_queue'

vi.mock('@/api/http/ingest_queue', () => ({
  ingestList: vi.fn(),
  subscribeIngestEvents: vi.fn(() => ({ close: vi.fn() })),
}))

import { ingestList, subscribeIngestEvents } from '@/api/http/ingest_queue'

const makeTask = (overrides: Partial<IngestTask> = {}): IngestTask => ({
  id: 't1',
  file_path: 'doc1.pdf',
  doc_id: 'doc1',
  status: 'processing',
  stage: 'moldet',
  progress_pct: 42,
  pages_total: 10,
  pages_done: 4,
  details: 'working',
  retry_count: 0,
  max_retries: 3,
  error: null,
  file_size_bytes: null,
  started_at: null,
  created_at: 1_000,
  updated_at: 2_000,
  priority: 0,
  ...overrides,
})

describe('useIngestPipeline', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('finds the most recent task matching docId', async () => {
    const mockList = vi.mocked(ingestList)
    mockList.mockResolvedValue([
      makeTask({ id: 'older', doc_id: 'doc1', created_at: 100, status: 'done' }),
      makeTask({ id: 'newer', doc_id: 'doc1', created_at: 200, status: 'pending' }),
      makeTask({ id: 'other', doc_id: 'doc2', created_at: 300, status: 'processing' }),
    ])

    const { result } = renderHook(() => useIngestPipeline('doc1', '/lib'))
    await waitFor(() => expect(result.current.task?.id).toBe('newer'))
    expect(result.current.progressPct).toBe(42)
  })

  it('re-fetches when docId changes', async () => {
    const mockList = vi.mocked(ingestList)
    mockList.mockResolvedValue([])

    const { rerender } = renderHook(
      ({ docId }) => useIngestPipeline(docId, '/lib'),
      { initialProps: { docId: 'doc1' } },
    )
    await waitFor(() => expect(mockList).toHaveBeenCalledWith('/lib'))

    mockList.mockClear()
    rerender({ docId: 'doc2' })
    await waitFor(() => expect(mockList).toHaveBeenCalledWith('/lib'))
  })

  it('does not return an embedState field', () => {
    const { result } = renderHook(() => useIngestPipeline('doc1', '/lib'))
    expect(result.current).not.toHaveProperty('embedState')
  })

  it('subscribes to SSE while a processing task is active', async () => {
    const mockList = vi.mocked(ingestList)
    mockList.mockResolvedValue([makeTask()])

    const { unmount } = renderHook(() => useIngestPipeline('doc1', '/lib'))
    await waitFor(() => expect(subscribeIngestEvents).toHaveBeenCalledTimes(1))
    expect(vi.mocked(subscribeIngestEvents).mock.calls[0][0]).toBe('/lib')
    expect(vi.mocked(subscribeIngestEvents).mock.calls[0][1]).toBe('t1')
    unmount()
  })
})
