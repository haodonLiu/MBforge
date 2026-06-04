import { EVT } from '../api/tauri-events'
import { useState, useEffect } from 'react'
import { listProjectDocuments, scanProjectFiles, indexProjectRust, type IndexResult } from '../api/tauri-bridge'
import { listen } from '@tauri-apps/api/event'
import type { DocumentEntry } from '../types'
import { useAppContext } from '../context/AppContext'

import PdfViewer from './project/PdfViewer'
import ProjectDashboard from './project/ProjectDashboard'
import MarkdownViewer from './MarkdownViewer'

export default function ProjectView() {
  const { projectRoot } = useAppContext()
  const [docs, setDocs] = useState<DocumentEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isIndexing, setIsIndexing] = useState(false)
  const [indexProgress, setIndexProgress] = useState<{ file: string; current: number; total: number } | null>(null)
  const [indexResult, setIndexResult] = useState<{ indexed: number; sections: number } | null>(null)
  const [error, setError] = useState('')

  const [selectedPdf, setSelectedPdf] = useState<DocumentEntry | null>(null)
  const [selectedMarkdown, setSelectedMarkdown] = useState<DocumentEntry | null>(null)

  const loadDocs = async () => {
    if (!projectRoot) return
    setIsLoading(true)
    setError('')
    try {
      const resp = await listProjectDocuments(projectRoot)
      if (resp.documents) {
        setDocs(resp.documents)
      }
    } catch (e) {
      console.error(e)
      setError('Failed to load documents')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadDocs()

    // Listen for per-document parse completion and refresh the list
    let unlistenResult: (() => void) | null = null
    const setup = async () => {
      unlistenResult = await listen<Record<string, unknown>>(EVT.DocResult, (event) => {
        const report = event.payload
        console.log('[doc-result] Parsed', report)
        // Refresh document list so newly-parsed items appear
        loadDocs()
      })
    }
    setup().catch(console.error)

    return () => {
      unlistenResult?.()
    }
  }, [])

  const handleScan = async () => {
    if (!projectRoot) {
      setError('项目根路径未设置，请先打开一个项目')
      return
    }
    setIsLoading(true)
    setError('')
    try {
      const resp = await scanProjectFiles(projectRoot)
      if (resp.documents) {
        if (resp.documents.length === 0) {
          setError('未找到 PDF 或 Markdown 文件')
        }
        setDocs(resp.documents)
      }
    } catch (e) {
      const msg = String(e)
      console.error('[ProjectView] Scan error:', msg)
      setError(msg.includes('not allowed') ? '扫描文件权限不足，请检查应用配置' : `扫描失败: ${msg}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleIndex = async () => {
    if (!projectRoot) return
    setIsIndexing(true)
    setError('')
    setIndexResult(null)
    setIndexProgress(null)

    scanProjectFiles(projectRoot).then(scanResp => {
      if (scanResp.documents) setDocs(scanResp.documents)
    }).catch(() => {})

    let total = 0
    const unlisten = await listen<{ stage: string; payload: Record<string, unknown> }>(EVT.DocProgress, (event) => {
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
      const result: IndexResult = await indexProjectRust(projectRoot)
      setIndexResult({ indexed: result.indexed, sections: result.sections })
      if (result.errors.length > 0) {
        console.warn('Index errors:', result.errors)
      }
      listProjectDocuments(projectRoot).then(r => { if (r.documents) setDocs(r.documents) })
    } catch (e) {
      const msg = String(e)
      if (msg.includes('ipc.localhost') || msg.includes('Failed to fetch') || msg.includes('ERR_CONNECTION_REFUSED')) {
        setError('索引引擎通信失败，请重启应用后重试')
      } else {
        setError(msg)
      }
    } finally {
      unlisten()
      setIndexProgress(null)
      setIsIndexing(false)
    }
  }

  const handleOpenFile = (doc: DocumentEntry) => {
    if (doc.doc_type === 'pdf') {
      setSelectedPdf(doc)
    } else if (doc.doc_type === 'md' || doc.path.toLowerCase().endsWith('.md')) {
      setSelectedMarkdown(doc)
    }
  }

  const handleCloseFile = () => {
    setSelectedPdf(null)
    setSelectedMarkdown(null)
  }

  if (selectedPdf) {
    return <PdfViewer doc={selectedPdf} projectRoot={projectRoot} onClose={handleCloseFile} />
  }

  if (selectedMarkdown) {
    return (
      <MarkdownViewer
        projectRoot={projectRoot}
        filePath={selectedMarkdown.path}
        onClose={handleCloseFile}
      />
    )
  }

  return (
    <ProjectDashboard
      projectRoot={projectRoot}
      docs={docs}
      isLoading={isLoading}
      isIndexing={isIndexing}
      indexProgress={indexProgress}
      indexResult={indexResult}
      error={error}
      onScan={handleScan}
      onIndex={handleIndex}
      onOpenFile={handleOpenFile}
      onDismissError={() => setError('')}
    />
  )
}
