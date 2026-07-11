import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('@/api/query/hooks', () => ({
  useIngestQueue: vi.fn(),
  useIngestStats: vi.fn(),
  useWorkerStatus: vi.fn(),
}))

vi.mock('@/api/query/useIngestSSE', () => ({
  useIngestSSE: vi.fn(),
}))

vi.mock('@/context/AppContext', () => ({
  useAppContext: vi.fn().mockReturnValue({ libraryRoot: '/tmp/lib' }),
}))

import { useIngestQueue, useIngestStats, useWorkerStatus } from '@/api/query/hooks'
import ProcessingQueue from '../ProcessingQueue'

function mockQueue(tasks: { id: string; status: string; doc_id: string }[]) {
  const now = Date.now()
  vi.mocked(useIngestQueue).mockReturnValue({
    data: tasks.map(t => ({
      id: t.id,
      doc_id: t.doc_id,
      file_path: `${t.doc_id}.pdf`,
      status: t.status,
      stage: '',
      progress_pct: 0,
      pages_total: 0,
      pages_done: 0,
      details: '',
      retry_count: 0,
      max_retries: 3,
      error: null,
      file_size_bytes: null,
      started_at: null,
      created_at: Math.floor(now / 1000) - 100,
      updated_at: Math.floor(now / 1000) - 50,
      priority: 0,
    })),
    isLoading: false,
    isError: false,
    error: null,
  } as ReturnType<typeof useIngestQueue>)

  vi.mocked(useIngestStats).mockReturnValue({
    data: { total: tasks.length, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0, avg_stage_durations_ms: [] },
    isLoading: false,
  } as ReturnType<typeof useIngestStats>)

  vi.mocked(useWorkerStatus).mockReturnValue({
    data: { status: 'online', ts: now },
  } as ReturnType<typeof useWorkerStatus>)
}

describe('ProcessingQueue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useIngestQueue).mockReturnValue({
      data: [],
      isLoading: true,
      isError: false,
    } as ReturnType<typeof useIngestQueue>)
    vi.mocked(useIngestStats).mockReturnValue({
      data: null,
      isLoading: true,
    } as ReturnType<typeof useIngestStats>)
    vi.mocked(useWorkerStatus).mockReturnValue({
      data: undefined,
    } as ReturnType<typeof useWorkerStatus>)
  })

  it('shows loading state', () => {
    render(<ProcessingQueue />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('shows empty state when queue is empty', () => {
    mockQueue([])
    render(<ProcessingQueue />)
    expect(screen.getByText(/no tasks/i)).toBeInTheDocument()
  })

  it('renders tasks when present', () => {
    mockQueue([
      { id: 't1', status: 'processing', doc_id: 'doc1' },
      { id: 't2', status: 'pending', doc_id: 'doc2' },
    ])
    render(<ProcessingQueue />)
    expect(screen.getByText('doc1.pdf')).toBeInTheDocument()
    expect(screen.getByText('doc2.pdf')).toBeInTheDocument()
  })
})
