import { useState, useEffect } from 'react'
import { listDocuments, scanProject } from '../api/client'
import { indexProjectRust, type IndexResult } from '../api/tauri-bridge'
import { listen } from '@tauri-apps/api/event'
import { FolderIcon, FileTextIcon, FlaskIcon, ExternalLinkIcon, SettingsIcon, ArrowLeftIcon } from './icons'
import type { DocumentEntry } from '../types'
import { getProjectRoot } from '../hooks/useProjectRoot'
import ErrorBanner from './ErrorBanner'
import StatCard from './project/StatCard'

export default function ProjectView() {
  const [projectRoot, setProjectRoot] = useState(getProjectRoot())
  const [docs, setDocs] = useState<DocumentEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isIndexing, setIsIndexing] = useState(false)
  const [indexProgress, setIndexProgress] = useState<{ file: string; current: number; total: number } | null>(null)
  const [indexResult, setIndexResult] = useState<{ indexed: number; sections: number } | null>(null)
  const [error, setError] = useState('')

  // PDF 阅读状态
  const [selectedPdf, setSelectedPdf] = useState<DocumentEntry | null>(null)

  const loadDocs = async () => {
    const root = getProjectRoot()
    if (!root) return
    setIsLoading(true)
    setError('')
    try {
      const resp = await listDocuments(root)
      if (resp.success && resp.documents) {
        setDocs(resp.documents)
      } else {
        setError(resp.error || 'Failed to load documents')
      }
    } catch (e) {
      console.error(e)
      setError('Failed to load documents')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    setProjectRoot(getProjectRoot())
    loadDocs()
  }, [])

  const handleScan = async () => {
    const root = getProjectRoot()
    if (!root) return
    setIsLoading(true)
    setError('')
    try {
      const resp = await scanProject(root)
      if (resp.success && resp.documents) {
        setDocs(resp.documents)
      } else {
        setError(resp.error || 'Scan failed')
      }
    } catch (e) {
      console.error(e)
      setError('Scan failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleIndex = async () => {
    const root = getProjectRoot()
    if (!root) return
    setIsIndexing(true)
    setError('')
    setIndexResult(null)
    setIndexProgress(null)

    // Scan first
    scanProject(root).then(scanResp => {
      if (scanResp.success && scanResp.documents) setDocs(scanResp.documents)
    }).catch(() => {})

    // Listen for progress events from Rust
    let total = 0
    const unlisten = await listen<{ stage: string; payload: Record<string, unknown> }>('doc-progress', (event) => {
      const payload = event.payload.payload
      const parser = payload.parser as string || ''
      if (parser.startsWith('indexing')) {
        const match = parser.match(/indexing\s+(\d+)\/(\d+)/)
        if (match) {
          const current = parseInt(match[1], 10)
          total = parseInt(match[2], 10)
          setIndexProgress({ file: parser, current, total })
        }
      }
    })

    try {
      const result: IndexResult = await indexProjectRust(root)
      setIndexResult({ indexed: result.indexed, sections: result.sections })
      if (result.errors.length > 0) {
        console.warn('Index errors:', result.errors)
      }
      listDocuments(root).then(r => { if (r.success && r.documents) setDocs(r.documents) })
    } catch (e) {
      setError(String(e))
    } finally {
      unlisten()
      setIndexProgress(null)
      setIsIndexing(false)
    }
  }

  const handleOpenPdf = (doc: DocumentEntry) => {
    if (doc.doc_type === 'pdf') {
      setSelectedPdf(doc)
    }
  }

  const handleClosePdf = () => {
    setSelectedPdf(null)
  }

  const projectName = projectRoot ? projectRoot.split('/').pop() || projectRoot : '未选择项目'

  // PDF 视图
  if (selectedPdf) {
    const pdfUrl = `/api/v1/file/pdf?path=${encodeURIComponent(selectedPdf.path)}`
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
        {/* 工具栏 */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          height: '48px',
          padding: '0 16px',
          background: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <button
            onClick={handleClosePdf}
            style={{
              width: '32px', height: '32px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'transparent', border: 'none', borderRadius: '6px',
              cursor: 'pointer', color: 'var(--text-secondary)',
            }}
          >
            <ArrowLeftIcon size={18} />
          </button>
          <span style={{
            fontSize: '13px', fontWeight: 500,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {selectedPdf.title || selectedPdf.path}
          </span>
        </div>
        {/* PDF 内容 */}
        <iframe
          src={pdfUrl}
          title={selectedPdf.title || 'PDF'}
          style={{
            flex: 1,
            width: '100%',
            border: 'none',
            background: '#525659',
          }}
        />
      </div>
    )
  }

  // 项目视图
  return (
    <div style={{
      flex: 1,
      padding: '32px',
      overflow: 'auto',
    }}>
      {error && <ErrorBanner message={error} onDismiss={() => setError('')} />}

      {/* 头部 */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '32px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{
            width: '48px',
            height: '48px',
            borderRadius: '12px',
            background: 'var(--accent-muted)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent)',
          }}>
            <FolderIcon size={24} />
          </div>
          <div>
            <h1 style={{
              fontSize: 'var(--font-size-title)',
              fontWeight: 600,
            }}>{projectName}</h1>
            <p style={{
              fontSize: '13px',
              color: 'var(--text-muted)',
            }}>{projectRoot || '请先打开或创建一个项目'}</p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-secondary" onClick={handleScan} disabled={!projectRoot || isLoading || isIndexing} style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 16px',
            fontSize: '13px',
          }}>
            <ExternalLinkIcon size={14} />
            {isLoading ? '扫描中...' : '扫描文件'}
          </button>
          <button className="btn btn-secondary" onClick={handleIndex} disabled={!projectRoot || isLoading || isIndexing} style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 16px',
            fontSize: '13px',
          }}>
            <FlaskIcon size={14} />
            {isIndexing ? '索引中...' : '索引文件'}
          </button>
          <button className="btn btn-secondary" style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 16px',
            fontSize: '13px',
          }}>
            <SettingsIcon size={14} />
            项目设置
          </button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: '16px',
        marginBottom: '32px',
      }}>
        <StatCard icon={<FileTextIcon size={18} />} value={String(docs.length)} label="文献" />
        <StatCard icon={<FlaskIcon size={18} />} value={indexResult ? String(indexResult.sections) : '—'} label="Sections" />
        <StatCard icon={<FileTextIcon size={18} />} value={String(docs.filter(d => d.indexed).length)} label="已索引" />
        <StatCard icon={<FolderIcon size={18} />} value={String(docs.length)} label="文件" />
      </div>

      {/* 索引进度条 */}
      {isIndexing && indexProgress && (
        <div style={{
          padding: '14px 18px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: '10px',
          marginBottom: '16px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '13px', fontWeight: 500 }}>
              正在索引 {indexProgress.current}/{indexProgress.total}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {indexProgress.file}
            </span>
          </div>
          <div className="download-progress-bar">
            <div
              className="download-progress-fill"
              style={{ width: `${Math.round(indexProgress.current * 100 / indexProgress.total)}%` }}
            />
          </div>
        </div>
      )}

      {indexResult && indexResult.indexed > 0 && (
        <div style={{
          padding: '12px 16px',
          background: 'rgba(22,163,74,0.1)',
          border: '1px solid rgba(22,163,74,0.3)',
          borderRadius: '8px',
          marginBottom: '16px',
          fontSize: '13px',
          color: '#16a34a',
        }}>
          已索引 {indexResult.indexed} 个 PDF，生成 {indexResult.sections} 个 section
        </div>
      )}

      {/* 文件列表 */}
      <h2 style={{
        fontSize: '16px',
        fontWeight: 600,
        marginBottom: '16px',
      }}>项目文件</h2>

      {docs.length === 0 ? (
        <div style={{
          padding: '40px',
          textAlign: 'center',
          color: 'var(--text-muted)',
          background: 'var(--bg-surface)',
          borderRadius: '12px',
          border: '1px solid var(--border)',
        }}>
          {projectRoot ? '暂无文件，点击"扫描文件"索引项目内容' : '请先打开或创建一个项目'}
        </div>
      ) : (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}>
          {docs.map(doc => (
            <div
              key={doc.doc_id}
              onClick={() => handleOpenPdf(doc)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '12px 16px',
                background: 'var(--bg-surface)',
                borderRadius: '8px',
                border: '1px solid var(--border)',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = 'var(--accent)'
                e.currentTarget.style.background = 'var(--accent-muted)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = 'var(--border)'
                e.currentTarget.style.background = 'var(--bg-surface)'
              }}
            >
              <FileTextIcon size={16} />
              <span style={{ flex: 1, fontSize: '14px' }}>{doc.title || doc.path}</span>
              <span style={{
                fontSize: '12px',
                color: 'var(--text-muted)',
                padding: '2px 8px',
                background: 'var(--bg-base)',
                borderRadius: '4px',
              }}>{doc.doc_type}</span>
              {doc.indexed ? (
                <span style={{
                  fontSize: '12px',
                  color: '#16a34a',
                  padding: '2px 8px',
                  background: 'rgba(22,163,74,0.1)',
                  borderRadius: '4px',
                }}>已索引</span>
              ) : (
                <span style={{
                  fontSize: '12px',
                  color: 'var(--text-muted)',
                  padding: '2px 8px',
                  background: 'var(--bg-base)',
                  borderRadius: '4px',
                }}>未索引</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
