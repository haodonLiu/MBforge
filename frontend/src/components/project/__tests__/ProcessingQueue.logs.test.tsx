import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import ProcessingQueue from '../ProcessingQueue'
import { EVT } from '../../../api/http-events'
import { ingestList, ingestDeleteTask } from '../../../api/http/ingest_queue'
import i18n from '../../../i18n'

const mockListen = vi.fn()

vi.mock('@tauri-apps/api/event', () => ({
  listen: (...args: unknown[]) => mockListen(...args),
  emit: vi.fn(),
}))

vi.mock('../../../api/tauri/ingest_queue', async () => {
  const actual = await vi.importActual<typeof import('../../../api/tauri/ingest_queue')>('../../../api/tauri/ingest_queue')
  return {
    ...actual,
    ingestList: vi.fn().mockResolvedValue([
      {
        id: 't1',
        file_path: '/docs/test.pdf',
        doc_id: 'doc1',
        status: 'processing',
        stage: 'ocr',
        progress_pct: 0.5,
        pages_total: 10,
        pages_done: 5,
        details: 'OCR 处理中',
        retry_count: 0,
        max_retries: 3,
        error: null,
        file_size_bytes: 1024,
        started_at: Date.now() / 1000,
        created_at: Date.now() / 1000,
        updated_at: Date.now() / 1000,
        priority: 0,
      },
    ]),
    ingestStats: vi.fn().mockResolvedValue({
      total: 1,
      pending: 0,
      processing: 1,
      done: 0,
      failed: 0,
      cancelled: 0,
      avg_stage_durations_ms: [0, 0, 0, 0, 0],
    }),
    ingestDeleteTask: vi.fn().mockResolvedValue(true),
  }
})

describe('ProcessingQueue logs', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.changeLanguage('zh')
    vi.mocked(ingestList).mockResolvedValue([
      {
        id: 't1',
        file_path: '/docs/test.pdf',
        doc_id: 'doc1',
        status: 'processing',
        stage: 'ocr',
        progress_pct: 0.5,
        pages_total: 10,
        pages_done: 5,
        details: 'OCR 处理中',
        retry_count: 0,
        max_retries: 3,
        error: null,
        file_size_bytes: 1024,
        started_at: Date.now() / 1000,
        created_at: Date.now() / 1000,
        updated_at: Date.now() / 1000,
        priority: 0,
      },
    ])
    mockListen.mockResolvedValue(() => {})
  })

  it('shows delete button for failed tasks and calls ingestDeleteTask', async () => {
    const failedTask = {
      id: 't2',
      file_path: '/docs/failed.pdf',
      doc_id: 'doc2',
      status: 'failed' as const,
      stage: 'parse',
      progress_pct: 0,
      pages_total: 1,
      pages_done: 0,
      details: '解析失败',
      retry_count: 3,
      max_retries: 3,
      error: 'parse error',
      file_size_bytes: 512,
      started_at: Date.now() / 1000,
      created_at: Date.now() / 1000,
      updated_at: Date.now() / 1000,
      priority: 0,
    }
    vi.mocked(ingestList).mockResolvedValue([failedTask])

    render(<ProcessingQueue projectRoot="/project" />)
    await waitFor(() => expect(screen.getByText('failed.pdf')).toBeInTheDocument())

    const deleteBtn = screen.getByRole('button', { name: /删除/ })
    expect(deleteBtn).toBeInTheDocument()

    fireEvent.click(deleteBtn)
    await waitFor(() =>
      expect(vi.mocked(ingestDeleteTask)).toHaveBeenCalledWith('/project', 't2'),
    )
  })

  it('expands log panel when chevron button is clicked', async () => {
    render(<ProcessingQueue projectRoot="/project" />)
    await waitFor(() => expect(screen.getByText('test.pdf')).toBeInTheDocument())

    const toggleBtn = screen.getByRole('button', { name: /显示日志|隐藏日志/ })
    fireEvent.click(toggleBtn)

    expect(screen.getByText(/暂无日志/)).toBeInTheDocument()
  })

  it('appends incoming ingest logs to the expanded panel', async () => {
    let ingestLogHandler: ((event: { payload: unknown }) => void) | null = null
    mockListen.mockImplementation((eventName: string, handler: unknown) => {
      if (eventName === EVT.IngestLog) {
        ingestLogHandler = handler as (event: { payload: unknown }) => void
      }
      return Promise.resolve(() => {})
    })

    render(<ProcessingQueue projectRoot="/project" />)
    await waitFor(() => expect(screen.getByText('test.pdf')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /显示日志|隐藏日志/ }))

    act(() => {
      ingestLogHandler?.({
        payload: {
          doc_id: 'doc1',
          stage: 'ocr',
          level: 'info',
          message: 'OCR 完成',
          ts_ms: Date.now(),
        },
      })
    })

    await waitFor(() => expect(screen.getByText('OCR 完成')).toBeInTheDocument())
  })
})
