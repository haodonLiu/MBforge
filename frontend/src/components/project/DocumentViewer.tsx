import { useCallback, useRef, useState, useMemo } from 'react'
import PdfViewer, { type PdfViewerHandle } from './PdfViewer'
import ReorganizedPane from './ReorganizedPane'
import WikiDrawer from './WikiDrawer'
import { useIsMobile } from '@/styles/responsive'
import type { DocumentEntry } from '@/types'

interface Props {
  doc: DocumentEntry
  libraryRoot: string
  onClose: () => void
}

type MobilePane = 'pdf' | 'markdown' | 'wiki'

/**
 * Composite document viewer: PDF on the left, reorganized markdown on the right,
 * wiki drawer (collapsible) on the far right.
 *
 * Responsive:
 * - <768px: stacked single-column (PDF only; wiki becomes bottom panel)
 * - >=768px: three-column grid
 *
 * Clicking a MoleCode block in the markdown pane jumps the PDF to the
 * corresponding page via the imperative PdfViewerHandle.
 */
export default function DocumentViewer({ doc, libraryRoot, onClose }: Props) {
  const pdfRef = useRef<PdfViewerHandle>(null)
  const [wikiCollapsed, setWikiCollapsed] = useState(false)
  const [mobilePane, setMobilePane] = useState<MobilePane>('pdf')
  const isMobile = useIsMobile()

  const handleMoleculeClick = useCallback((info: { page: number }) => {
    pdfRef.current?.setCurrentPage(info.page)
  }, [])

  // Responsive grid columns.
  const gridTemplateColumns = useMemo(() => {
    if (isMobile) return '1fr' // single column
    return wikiCollapsed
      ? 'minmax(0, 1.1fr) minmax(0, 1fr) auto'
      : 'minmax(0, 1.1fr) minmax(0, 1fr) 320px'
  }, [isMobile, wikiCollapsed])

  // On mobile, only show the middle (wiki) pane below the PDF.

  return (
    <div className="document-viewer" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {isMobile && (
        <div className="document-viewer-mobile-tabs" role="tablist" aria-label="Document panes">
          {(['pdf', 'markdown', 'wiki'] as const).map((pane) => (
            <button
              key={pane}
              type="button"
              role="tab"
              aria-selected={mobilePane === pane}
              className={mobilePane === pane ? 'is-active' : ''}
              onClick={() => setMobilePane(pane)}
            >
              {pane === 'pdf' ? 'PDF' : pane === 'markdown' ? 'Markdown' : 'Wiki'}
            </button>
          ))}
        </div>
      )}
      {/* Body: PDF, reorganized markdown, and Wiki panes. */}
      <div
        className="document-viewer-body"
        style={{
          flex: 1,
          display: 'grid',
          gridTemplateColumns,
          minHeight: 0,
          overflow: 'hidden',
        }}
      >
        {(!isMobile || mobilePane === 'pdf') && (
          <div className="document-viewer-pane" style={isMobile ? {} : { borderRight: '1px solid var(--border)' }}>
            <PdfViewer ref={pdfRef} doc={doc} libraryRoot={libraryRoot} onClose={onClose} />
          </div>
        )}

        {(!isMobile || mobilePane === 'markdown') && (
          <ReorganizedPane
            docId={doc.doc_id}
            libraryRoot={libraryRoot}
            onMoleculeClick={handleMoleculeClick}
          />
        )}

        {(!isMobile || mobilePane === 'wiki') && (
          <WikiDrawer
            docId={doc.doc_id}
            libraryRoot={libraryRoot}
            collapsed={wikiCollapsed}
            onToggle={() => setWikiCollapsed(v => !v)}
          />
        )}
      </div>
    </div>
  )
}
