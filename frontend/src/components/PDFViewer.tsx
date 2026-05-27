import { useState, useRef } from 'react'
import { PdfIcon, XIcon } from './icons'

interface PDFViewerProps {
  filePath?: string
  onClose?: () => void
}

export default function PDFViewer({ filePath, onClose }: PDFViewerProps) {
  const [error, setError] = useState('')
  const iframeRef = useRef<HTMLIFrameElement>(null)

  if (!filePath) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--text-secondary)',
        gap: '16px',
      }}>
        <PdfIcon size={48} />
        <p>选择一个 PDF 文件查看</p>
      </div>
    )
  }

  // Use the backend to serve the PDF file
  const pdfUrl = `/api/v1/file/pdf?path=${encodeURIComponent(filePath)}`

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 16px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-surface)',
      }}>
        <span style={{
          fontSize: '13px',
          color: 'var(--text-secondary)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          maxWidth: '80%',
        }}>
          {filePath.split(/[/\\]/).pop()}
        </span>
        {onClose && (
          <button
            onClick={onClose}
            style={{
              width: '24px',
              height: '24px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: '4px',
              border: 'none',
              background: 'transparent',
              color: 'var(--text-muted)',
              cursor: 'pointer',
            }}
          >
            <XIcon size={14} />
          </button>
        )}
      </div>
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {error ? (
          <div style={{
            padding: '24px',
            textAlign: 'center',
            color: 'var(--text-muted)',
          }}>
            <PdfIcon size={32} />
            <p style={{ marginTop: '12px' }}>{error}</p>
          </div>
        ) : (
          <iframe
            ref={iframeRef}
            src={pdfUrl}
            style={{
              width: '100%',
              height: '100%',
              border: 'none',
            }}
            onError={() => setError('无法加载 PDF 文件')}
            title="PDF Viewer"
          />
        )}
      </div>
    </div>
  )
}
