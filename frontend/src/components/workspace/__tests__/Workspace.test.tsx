import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mock hooks before any imports that use them.
vi.mock('@/api/query/hooks', () => ({
  useDocuments: vi.fn(),
  useImportDocument: vi.fn(),
  useDeleteDocument: vi.fn(),
}))

vi.mock('@/context/AppContext', () => ({
  useAppContext: vi.fn(),
  AppProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// i18n mock — return key as-is when t() is called.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}))

import { useDocuments, useImportDocument } from '@/api/query/hooks'
import { useDeleteDocument } from '@/api/query/hooks'
import { useAppContext } from '@/context/AppContext'
import Workspace from '../Workspace'

function mockAppContext(overrides?: Record<string, unknown>) {
  vi.mocked(useAppContext).mockReturnValue({
    libraryRoot: '/tmp/lib',
    activeCollectionId: null,
    openTab: vi.fn(),
    ...overrides,
  } as unknown as ReturnType<typeof useAppContext>)
}

function mockDocuments(docs: { doc_id: string; title: string; status: string }[]) {
  vi.mocked(useDocuments).mockReturnValue({
    data: { documents: docs.map(d => ({ ...d, file_name: `${d.doc_id}.pdf`, page_count: 3, created_at: '2026-01-01' })) },
    isLoading: false,
    isError: false,
    error: null,
    dataUpdatedAt: Date.now(),
  } as unknown as ReturnType<typeof useDocuments>)
}

function mockDeleteDocument() {
  vi.mocked(useDeleteDocument).mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useDeleteDocument>)
}

function renderWorkspace() {
  return render(<Workspace />)
}

describe('Workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAppContext()
    // Default: loading state
    vi.mocked(useDocuments).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useDocuments>)
    vi.mocked(useImportDocument).mockReturnValue({
      mutateAsync: vi.fn(),
    } as unknown as ReturnType<typeof useImportDocument>)
    mockDeleteDocument()
  })

  it('shows loading state', () => {
    renderWorkspace()
    expect(screen.getByTestId('workspace-skeleton')).toHaveAttribute('aria-busy', 'true')
  })

  it('shows empty state when no documents', () => {
    mockDocuments([])
    renderWorkspace()
    // i18n t() returns key "library.noDocuments" in test.
    expect(screen.getByText('library.noDocuments')).toBeInTheDocument()
  })

  it('renders document list', () => {
    mockDocuments([
      { doc_id: 'doc1', title: 'Test Paper 1', status: 'ready' },
      { doc_id: 'doc2', title: 'Test Paper 2', status: 'indexing' },
    ])
    renderWorkspace()
    expect(screen.getByText('Test Paper 1')).toBeInTheDocument()
    expect(screen.getByText('Test Paper 2')).toBeInTheDocument()
  })

  it('shows error state when query fails', () => {
    vi.mocked(useDocuments).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Network error'),
    } as unknown as ReturnType<typeof useDocuments>)
    renderWorkspace()
    expect(screen.getByText('Failed to load documents. Please try again.')).toBeInTheDocument()
    expect(screen.getByText('Retry')).toBeInTheDocument()
  })

  it('shows import button in empty state when no collection filter', () => {
    mockDocuments([])
    renderWorkspace()
    const importBtns = screen.getAllByText('library.importPdf')
    expect(importBtns.length).toBeGreaterThanOrEqual(2)
  })

  it('calls openTab when document card is clicked', () => {
    const openTab = vi.fn()
    mockAppContext({ openTab })
    mockDocuments([{ doc_id: 'doc1', title: 'Clickable Doc', status: 'ready' }])
    renderWorkspace()
    screen.getByText('Clickable Doc').click()
    expect(openTab).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'document', title: 'Clickable Doc' }),
    )
  })

  it('deletes a document after confirmation without opening it', () => {
    const deleteDocument = vi.fn().mockResolvedValue({ success: true })
    vi.mocked(useDeleteDocument).mockReturnValue({
      mutateAsync: deleteDocument,
      isPending: false,
    } as unknown as ReturnType<typeof useDeleteDocument>)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockDocuments([{ doc_id: 'doc1', title: 'Deletable Doc', status: 'pending' }])
    renderWorkspace()

    const deleteButton = screen.getByRole('button', { name: 'doc.delete' })
    deleteButton.click()

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('doc.deleteConfirm'))
    expect(deleteDocument).toHaveBeenCalledWith('doc1')
  })

  it('keeps the document when deletion is cancelled', () => {
    const deleteDocument = vi.fn()
    vi.mocked(useDeleteDocument).mockReturnValue({
      mutateAsync: deleteDocument,
      isPending: false,
    } as unknown as ReturnType<typeof useDeleteDocument>)
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mockDocuments([{ doc_id: 'doc1', title: 'Kept Doc', status: 'pending' }])
    renderWorkspace()

    screen.getByRole('button', { name: 'doc.delete' }).click()

    expect(deleteDocument).not.toHaveBeenCalled()
    expect(screen.getByText('Kept Doc')).toBeInTheDocument()
  })
})
