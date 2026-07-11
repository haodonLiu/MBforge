import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mock child components to isolate DocumentViewer tests.
vi.mock('../PdfViewer', () => ({
  default: vi.fn(() => <div data-testid="pdf-viewer">PDF</div>),
  PdfViewerHandle: {} as never,
}))

vi.mock('../ReorganizedPane', () => ({
  default: vi.fn(() => <div data-testid="reorganized-pane">Reorg</div>),
}))

vi.mock('../WikiDrawer', () => ({
  default: vi.fn(({ collapsed }: { collapsed: boolean }) => (
    <div data-testid="wiki-drawer" data-collapsed={collapsed}>Wiki</div>
  )),
}))

import DocumentViewer from '../DocumentViewer'

const mockDoc = {
  doc_id: 'test-doc-1',
  path: 'test.pdf',
  doc_type: 'pdf' as const,
  title: 'Test Document',
  indexed: false,
}

describe('DocumentViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders PDF viewer and markdown/reorganized panes', () => {
    render(<DocumentViewer doc={mockDoc} libraryRoot="/tmp/lib" onClose={vi.fn()} />)
    expect(screen.getByTestId('pdf-viewer')).toBeInTheDocument()
    expect(screen.getByTestId('reorganized-pane')).toBeInTheDocument()
    expect(screen.getByTestId('wiki-drawer')).toBeInTheDocument()
  })

  it('shows document ID in toolbar', () => {
    render(<DocumentViewer doc={mockDoc} libraryRoot="/tmp/lib" onClose={vi.fn()} />)
    expect(screen.getByText('test-doc-1')).toBeInTheDocument()
  })
})
