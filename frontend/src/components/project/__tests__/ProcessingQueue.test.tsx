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

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
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
  } as unknown as ReturnType<typeof useIngestQueue>)

  vi.mocked(useIngestStats).mockReturnValue({
    data: { total: tasks.length, by_status: {} },
    isLoading: false,
  } as unknown as ReturnType<typeof useIngestStats>)

  vi.mocked(useWorkerStatus).mockReturnValue({
    data: { status: 'online', ts: now },
  } as unknown as ReturnType<typeof useWorkerStatus>)
}

describe('ProcessingQueue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useIngestQueue).mockReturnValue({
      data: [],
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useIngestQueue>)
    vi.mocked(useIngestStats).mockReturnValue({
      data: null,
      isLoading: true,
    } as unknown as ReturnType<typeof useIngestStats>)
    vi.mocked(useWorkerStatus).mockReturnValue({
      data: undefined,
    } as unknown as ReturnType<typeof useWorkerStatus>)
  })

  it('shows loading state', () => {
    render(<ProcessingQueue />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('shows empty state when queue is empty', () => {
    mockQueue([])
    render(<ProcessingQueue />)
    // i18n returns key as-is.
    expect(screen.getByText('queue.emptyHint')).toBeInTheDocument()
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

  it('renders when stats is missing avg_stage_durations_ms', () => {
    mockQueue([{ id: 't1', status: 'processing', doc_id: 'doc1' }])
    vi.mocked(useIngestStats).mockReturnValue({
      data: { total: 1, by_status: { processing: 1 } },
      isLoading: false,
    } as unknown as ReturnType<typeof useIngestStats>)
    render(<ProcessingQueue />)
    // No throw — and the "recent 5 average" pill is hidden because no
    // duration data is present.
    expect(screen.queryByText('queue.recent5')).not.toBeInTheDocument()
  })
})
