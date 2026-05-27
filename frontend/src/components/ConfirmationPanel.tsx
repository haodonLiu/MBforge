export interface PageClassification {
  pageIdx: number
  isScanned: boolean
  hasMolecularPatterns: boolean
  recommendedMethod: string
}

interface ConfirmationPanelProps {
  documentType: 'text' | 'scanned' | 'mixed'
  totalPages: number
  pages: PageClassification[]
  estimatedCost: number
  detectedMolecules: number
  onProceed: () => void
  onOverride: (method: string) => void
  onReviewMolecules: () => void
}

export default function ConfirmationPanel({
  documentType,
  totalPages,
  pages,
  estimatedCost,
  detectedMolecules,
  onProceed,
  onOverride,
  onReviewMolecules,
}: ConfirmationPanelProps) {
  const scannedPages = pages.filter((p) => p.isScanned).length
  const textPages = totalPages - scannedPages

  const handleOverride = () => {
    const method = prompt(
      'Enter override method (e.g. "ocr_all", "text_only", "hybrid"):',
    )
    if (method) {
      onOverride(method)
    }
  }

  return (
    <div className="confirmation-panel">
      <div className="confirmation-header">
        <h2>PDF Classification Results</h2>
      </div>

      <div className="confirmation-info">
        <div className="confirmation-info-row">
          <span className="confirmation-label">Document Type</span>
          <span
            className={`confirmation-value confirmation-type confirmation-type-${documentType}`}
          >
            {documentType.charAt(0).toUpperCase() + documentType.slice(1)}
          </span>
        </div>
        <div className="confirmation-info-row">
          <span className="confirmation-label">Total Pages</span>
          <span className="confirmation-value">{totalPages}</span>
        </div>
        <div className="confirmation-info-row">
          <span className="confirmation-label">Text Pages</span>
          <span className="confirmation-value confirmation-text-count">
            {textPages}
          </span>
        </div>
        <div className="confirmation-info-row">
          <span className="confirmation-label">Scanned Pages</span>
          <span className="confirmation-value confirmation-scanned-count">
            {scannedPages}
          </span>
        </div>
      </div>

      <div className="confirmation-page-map">
        <h3>Page Map</h3>
        <div className="confirmation-pages">
          {pages.map((page) => (
            <div
              key={page.pageIdx}
              className={`confirmation-page ${page.isScanned ? 'scanned' : 'text'} ${page.hasMolecularPatterns ? 'has-molecules' : ''}`}
              title={`Page ${page.pageIdx + 1}: ${page.isScanned ? 'Scanned' : 'Text'}${page.hasMolecularPatterns ? ' (molecular patterns detected)' : ''}`}
            >
              {page.isScanned ? 'S' : 'T'}
            </div>
          ))}
        </div>
        <div className="confirmation-legend">
          <span className="confirmation-legend-item">
            <span className="confirmation-page text small">T</span> Text page
          </span>
          <span className="confirmation-legend-item">
            <span className="confirmation-page scanned small">S</span> Scanned
            page
          </span>
          <span className="confirmation-legend-item">
            <span className="confirmation-page text small has-molecules">T</span>{' '}
            Has molecular patterns
          </span>
        </div>
      </div>

      <div className="confirmation-recommendations">
        <h3>Recommended Methods</h3>
        <ul>
          <li>
            <span className="confirmation-method-label">Text pages ({textPages}):</span>{' '}
            Direct text extraction (low cost)
          </li>
          <li>
            <span className="confirmation-method-label">
              Scanned pages ({scannedPages}):
            </span>{' '}
            OCR + VLM processing (higher cost)
          </li>
        </ul>
      </div>

      <div className="confirmation-summary">
        <div className="confirmation-info-row">
          <span className="confirmation-label">Estimated Cost</span>
          <span className="confirmation-value confirmation-cost">
            ${estimatedCost.toFixed(2)}
          </span>
        </div>
        <div className="confirmation-info-row">
          <span className="confirmation-label">Detected Molecules</span>
          <span className="confirmation-value confirmation-molecules">
            {detectedMolecules}
          </span>
        </div>
      </div>

      <div className="confirmation-actions">
        <button className="btn btn-secondary" onClick={handleOverride}>
          Override Method
        </button>
        <button className="btn btn-secondary" onClick={onReviewMolecules}>
          Review Molecules
        </button>
        <button className="btn btn-primary" onClick={onProceed}>
          Proceed with Indexing
        </button>
      </div>
    </div>
  )
}
