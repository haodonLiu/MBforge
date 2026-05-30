import { useState, useRef } from 'react'
import { PdfIcon, XIcon } from './icons'
import Toolbar from './ui/Toolbar'
import IconButton from './ui/IconButton'
import EmptyState from './ui/EmptyState'

interface PDFViewerProps {
  filePath?: string
  onClose?: () => void
}

export default function PDFViewer({ filePath, onClose }: PDFViewerProps) {
  const [error, setError] = useState('')
  const iframeRef = useRef<HTMLIFrameElement>(null)

  if (!filePath) {
    return (
      <EmptyState
        message="选择一个 PDF 文件查看"
        icon={<PdfIcon size={48} />}
      />
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
      <Toolbar title={filePath.split(/[/\\]/).pop()}>
        {onClose && (
          <IconButton onClick={onClose} size={24}>
            <XIcon size={14} />
          </IconButton>
        )}
      </Toolbar>
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {error ? (
          <EmptyState
            message={error}
            icon={<PdfIcon size={32} />}
            style={{ padding: '24px' }}
          />
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
