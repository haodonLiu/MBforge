interface Props {
  pdfScale: number
  onZoomIn: () => void
  onZoomOut: () => void
  onZoomReset: () => void
  currentPage: number
  pdfPageCount: number
  pageJumpInput: string
  onPageJumpInputChange: (v: string) => void
  onJumpToPage: () => void
  onPrevPage: () => void
  onNextPage: () => void
}

export default function PdfFloatingControls(props: Props) {
  const {
    pdfScale, onZoomIn, onZoomOut, onZoomReset,
    currentPage, pdfPageCount, pageJumpInput, onPageJumpInputChange, onJumpToPage,
    onPrevPage, onNextPage,
  } = props

  return (
    <div className="pdf-floating-bar">
      <button className="pdf-floating-btn" onClick={onPrevPage} disabled={currentPage <= 1} title="上一页">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m15 18-6-6 6-6" />
        </svg>
      </button>

      <div className="pdf-floating-page">
        <input
          type="text"
          value={pageJumpInput || currentPage}
          onChange={e => onPageJumpInputChange(e.target.value.replace(/\D/g, ''))}
          onKeyDown={e => { if (e.key === 'Enter') onJumpToPage() }}
          onBlur={() => onPageJumpInputChange('')}
          className="pdf-floating-page-input"
        />
        <span className="pdf-floating-page-sep">/</span>
        <span className="pdf-floating-page-total">{pdfPageCount || '?'}</span>
      </div>

      <button className="pdf-floating-btn" onClick={onNextPage} disabled={currentPage >= (pdfPageCount || 1)} title="下一页">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m9 18 6-6-6-6" />
        </svg>
      </button>

      <div className="pdf-floating-divider" />

      <button className="pdf-floating-btn" onClick={onZoomOut} title="缩小">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 12h14" />
        </svg>
      </button>

      <button className="pdf-floating-zoom" onClick={onZoomReset} title="重置缩放">
        {Math.round(pdfScale * 100)}%
      </button>

      <button className="pdf-floating-btn" onClick={onZoomIn} title="放大">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
      </button>
    </div>
  )
}
