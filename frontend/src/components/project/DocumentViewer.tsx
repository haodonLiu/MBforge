import { useCallback, useRef, useState, useMemo } from 'react'
import PdfViewer, { type PdfViewerHandle } from './PdfViewer'
import ReorganizedPane from './ReorganizedPane'
import WikiDrawer from './WikiDrawer'
import IconButton from '@/components/ui/IconButton'
import { ArrowLeftIcon } from '@/components/icons'
import { useIsMobile } from '@/styles/responsive'
import type { DocumentEntry } from '@/types'

interface Props {
  doc: DocumentEntry
  libraryRoot: string
  onClose: () => void
}

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
  const isMobile = useIsMobile()

  const handleMoleculeClick = useCallback((info: { page: number }) => {
    pdfRef.current?.setCurrentPage(info.page)
  }, [])

  // Responsive grid columns.
  const gridTemplateColumns = useMemo(() => {
    if (isMobile) return '1fr' // single column
    return wikiCollapsed ? '1fr 1fr auto' : '1fr 1fr 320px'
  }, [isMobile, wikiCollapsed])

  // On mobile, only show the middle (wiki) pane below the PDF.

  return (
    <div className="document-viewer" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Top toolbar */}
      <div className="document-viewer-toolbar">
        <IconButton size={40} onClick={onClose} title="关闭">
          <ArrowLeftIcon size={18} />
        </IconButton>
        <div className="document-viewer-title">{doc.doc_id}</div>
      </div>

      {/* Body: 3-column layout (responsive) */}
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
        {/* Left: PDF viewer */}
        <div className="document-viewer-pane" style={isMobile ? {} : { borderRight: '1px solid var(--border)' }}>
          <PdfViewer ref={pdfRef} doc={doc} libraryRoot={libraryRoot} onClose={onClose} />
        </div>

        {!isMobile && (
          <>
            {/* Middle: Reorganized markdown with MoleCode */}
            <ReorganizedPane
              docId={doc.doc_id}
              libraryRoot={libraryRoot}
              onMoleculeClick={handleMoleculeClick}
            />

            {/* Right: Wiki drawer (collapsible) */}
            <WikiDrawer
              docId={doc.doc_id}
              libraryRoot={libraryRoot}
              collapsed={wikiCollapsed}
              onToggle={() => setWikiCollapsed(v => !v)}
            />
          </>
        )}
      </div>
    </div>
  )
}