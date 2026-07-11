import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mock hooks before any imports that use them.
vi.mock('@/api/query/hooks', () => ({
  useDocuments: vi.fn(),
  useImportDocument: vi.fn(),
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
  })

  it('shows loading state', () => {
    renderWorkspace()
    expect(screen.getByText('Loading...')).toBeInTheDocument()
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
})
