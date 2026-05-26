import { useState } from 'react'
import { PdfIcon } from './icons'

export default function PDFViewer() {
  const [file, setFile] = useState<File | null>(null)

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const dropped = e.dataTransfer.files[0]
    if (dropped?.type === 'application/pdf') {
      setFile(dropped)
    }
  }

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {file ? (
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-secondary)',
        }}>
          <PdfIcon size={48} />
          <p style={{ marginTop: '16px' }}>{file.name}</p>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            PDF 渲染即将集成
          </p>
        </div>
      ) : (
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '16px',
            color: 'var(--text-secondary)',
          }}
          onDrop={handleDrop}
          onDragOver={e => e.preventDefault()}
        >
          <PdfIcon size={48} />
          <p>拖拽 PDF 文件到此处</p>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            或点击选择文件
          </p>
        </div>
      )}
    </div>
  )
}
