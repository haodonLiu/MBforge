import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DocumentList from '../DocumentList'
import type { DocumentEntry } from '../../../types'

vi.mock('@tauri-apps/plugin-dialog', () => ({
  ask: vi.fn(() => Promise.resolve(true)),
}))

vi.mock('../../../api/tauri/project', () => ({
  deleteDocument: vi.fn(() => Promise.resolve()),
  reingestDocument: vi.fn(() => Promise.resolve()),
}))

vi.mock('../../../api/tauri/pdf', () => ({
  inspectPdf: vi.fn(() => Promise.resolve()),
  confirmOcr: vi.fn(() => Promise.resolve()),
}))

vi.mock('../../../api/tauri/ingest_queue', () => ({
  ingestEnqueue: vi.fn(() => Promise.resolve()),
  trackSelfTriggeredDoc: vi.fn(),
}))

vi.mock('../../../hooks/useToast', () => ({
  showToast: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const makeDoc = (overrides: Partial<DocumentEntry> = {}): DocumentEntry => ({
  doc_id: 'doc-1',
  path: 'projects/doc-1/source.pdf',
  source_path: 'projects/doc-1/source.pdf',
  doc_type: 'pdf',
  title: 'Test Paper',
  indexed: true,
  hash: 'abc',
  inspector_status: 'text_based',
  text_status: 'done',
  ocr_status: 'not_processed',
  moldet_status: 'has_molecule',
  index_status: 'done',
  ...overrides,
})

describe('DocumentList actions', () => {
  it('renders delete and reingest buttons for indexed pdf', () => {
    render(<DocumentList docs={[makeDoc()]} isLoading={false} projectRoot="/tmp/p" onOpenFile={vi.fn()} />)
    expect(screen.getByTitle('doc.reingest')).toBeInTheDocument()
    expect(screen.getByTitle('doc.delete')).toBeInTheDocument()
  })

  it('does not render action buttons for non-pdf documents', () => {
    render(<DocumentList docs={[makeDoc({ doc_type: 'markdown', path: 'notes/readme.md' })]} isLoading={false} projectRoot="/tmp/p" onOpenFile={vi.fn()} />)
    expect(screen.queryByTitle('doc.reingest')).not.toBeInTheDocument()
    expect(screen.queryByTitle('doc.delete')).not.toBeInTheDocument()
  })
})
