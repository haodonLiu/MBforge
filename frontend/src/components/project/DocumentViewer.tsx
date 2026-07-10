import { useCallback, useRef, useState } from 'react'
import PdfViewer, { type PdfViewerHandle } from './PdfViewer'
import ReorganizedPane from './ReorganizedPane'
import WikiDrawer from './WikiDrawer'
import IconButton from '@/components/ui/IconButton'
import { ArrowLeftIcon } from '@/components/icons'
import type { DocumentEntry } from '@/types'

interface Props {
  doc: DocumentEntry
  libraryRoot: string
  onClose: () => void
}

/**
 * Composite document viewer: PDF on the left, reorganized markdown on the right,
 * wiki drawer (collapsible) on the far right. Clicking a MoleCode block in the
 * markdown pane jumps the PDF to the corresponding page.
 */
export default function DocumentViewer({ doc, libraryRoot, onClose }: Props) {
  const pdfRef = useRef<PdfViewerHandle>(null)
  const [wikiCollapsed, setWikiCollapsed] = useState(false)

  const handleMoleculeClick = useCallback((info: { page: number }) => {
    pdfRef.current?.setCurrentPage(info.page)
  }, [])

  return (
    <div className="document-viewer" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Top toolbar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 12px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-surface)',
        height: 44,
      }}>
        <IconButton size={32} onClick={onClose} title="关闭">
          <ArrowLeftIcon size={18} />
        </IconButton>
        <div style={{ fontSize: 13, fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {doc.doc_id}
        </div>
      </div>

      {/* Body: 3-column layout */}
      <div style={{
        flex: 1,
        display: 'grid',
        gridTemplateColumns: wikiCollapsed
          ? '1fr 1fr auto'
          : '1fr 1fr 320px',
        minHeight: 0,
        overflow: 'hidden',
      }}>
        {/* Left: PDF viewer (imperative handle exposed via ref) */}
        <div style={{ borderRight: '1px solid var(--border)', minHeight: 0, overflow: 'hidden' }}>
          <PdfViewer ref={pdfRef} doc={doc} libraryRoot={libraryRoot} onClose={onClose} />
        </div>

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
      </div>
    </div>
  )
}