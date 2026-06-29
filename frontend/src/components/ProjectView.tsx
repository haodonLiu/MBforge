import { EVT } from '../api/tauri-events'
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { listProjectDocuments, scanProjectFiles, enqueueUnresolvedDocuments, indexProject, type IndexResult, type ScanWarning } from '../api/tauri'
import { batchQuickMoldetScan } from '../api/tauri/detection_cache'
import { molAdminStoreStats } from '../api/tauri/molecule_admin'
import type { DocumentEntry } from '../types'
import { useAppContext } from '../context/AppContext'
import { showToast } from '../hooks/useToast'
import { PAPERS_DIR, NOTES_DIR } from '../config/folderLayout'

import PdfViewer from './project/PdfViewer'
import ProjectDashboard from './project/ProjectDashboard'
import MarkdownViewer from './MarkdownViewer'

interface ProjectViewProps {
  onFileActive?: (active: boolean) => void
}

export default function ProjectView({ onFileActive }: ProjectViewProps) {
  const { t } = useTranslation()
  const { projectRoot, activeFile, setActiveFile } = useAppContext()
  const [docs, setDocs] = useState<DocumentEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncStage, setSyncStage] = useState<'scanning' | 'indexing' | null>(null)
  const [indexProgress, setIndexProgress] = useState<{ file: string; current: number; total: number } | null>(null)
  const [indexResult, setIndexResult] = useState<{ indexed: number; sections: number } | null>(null)
  const [error, setError] = useState('')
  const [scanWarnings, setScanWarnings] = useState<ScanWarning[]>([])
  const [moleculeStats, setMoleculeStats] = useState<{ total: number; confirmed: number } | null>(null)

  const [selectedPdf, setSelectedPdf] = useState<DocumentEntry | null>(null)
  const [selectedMarkdown, setSelectedMarkdown] = useState<DocumentEntry | null>(null)
  const [isMoldetScanning, setIsMoldetScanning] = useState(false)
  const [moldetProgress, setMoldetProgress] = useState<{ current: number; total: number } | null>(null)
  const [moldetResult, setMoldetResult] = useState<{ scanned: number; withMolecules: number } | null>(null)

  const hasFileOpen = selectedPdf !== null || selectedMarkdown !== null
  useEffect(() => {
    onFileActive?.(hasFileOpen)
  }, [hasFileOpen, onFileActive])

  const loadDocs = async () => {
    if (!projectRoot) return
    setIsLoading(true)
    setError('')
    try {
      const [docResp, molResp] = await Promise.all([
        listProjectDocuments(projectRoot),
        molAdminStoreStats(projectRoot).catch(() => null),
      ])
      if (docResp.documents) {
        setDocs(docResp.documents)
      }
      if (molResp) {
        const total = (molResp.total as number) || 0
        const pending = (molResp.pending as number) || 0
        setMoleculeStats({ total, confirmed: total - pending })
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
  }, [])

  const handleSync = async () => {
    if (!projectRoot) {
      setError(t('project.noProjectRoot'))
      return
    }
    setIsSyncing(true)
    setSyncStage('scanning')
    setError('')
    setScanWarnings([])
    setIndexResult(null)
    setIndexProgress(null)

    try {
      const scanResp = await scanProjectFiles(projectRoot)
      setDocs(scanResp.documents)
      setScanWarnings(scanResp.warnings ?? [])
      void enqueueUnresolvedDocuments(projectRoot).catch((e) => console.warn('enqueueUnresolvedDocuments failed:', e))

      if (scanResp.documents.length === 0 && (scanResp.warnings ?? []).length === 0) {
        setError(t('project.noFilesFound', { papers: PAPERS_DIR, notes: NOTES_DIR }))
        return
      }

      setSyncStage('indexing')

      const INDEX_TIMEOUT_MS = 5 * 60 * 1000
      try {
        const result: IndexResult = await Promise.race([
          indexProject(projectRoot),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error(t('project.indexTimeout'))), INDEX_TIMEOUT_MS)
          ),
        ])
        setIndexResult({ indexed: result.indexed, sections: result.sections })
        if (result.errors.length > 0) {
          console.warn('Index errors:', result.errors)
        }
        listProjectDocuments(projectRoot).then(r => { if (r.documents) setDocs(r.documents) })
      } catch (e) {
        const msg = String(e)
        if (msg.includes('ipc.localhost') || msg.includes('Failed to fetch') || msg.includes('ERR_CONNECTION_REFUSED')) {
          setError(t('project.indexEngineFailed'))
        } else if (msg.includes('索引超时')) {
          setError(t('project.indexOperationTimeout'))
        } else {
          setError(msg)
        }
      } finally {
        setIndexProgress(null)
      }
    } catch (e) {
      const msg = String(e)
      console.error('[ProjectView] Sync error:', msg)
      setError(msg.includes('not allowed') ? t('project.scanPermissionDenied') : t('project.scanFailed', { error: msg }))
    } finally {
      setIsSyncing(false)
      setSyncStage(null)
    }
  }

  const handleOpenFile = (doc: DocumentEntry) => {
    if (doc.doc_type === 'pdf') {
      setSelectedPdf(doc)
    } else if (doc.doc_type === 'markdown' || doc.path.toLowerCase().endsWith('.md')) {
      setSelectedMarkdown(doc)
    }
  }

  // 响应侧边栏文件树选中的文件，在应用内打开
  useEffect(() => {
    if (!activeFile) return
    if (isLoading) return // 等待文档列表加载完成

    const normalizedActive = activeFile.path.replace(/\\/g, '/')
    const doc = docs.find(d => {
      const dPath = d.path.replace(/\\/g, '/')
      return dPath === normalizedActive || normalizedActive.endsWith('/' + dPath)
    })

    const fallbackDoc: DocumentEntry = {
      doc_id: activeFile.path,
      path: activeFile.path,
      doc_type: activeFile.type === 'pdf' ? 'pdf' : 'md',
      title: activeFile.path.split(/[\\/]/).pop() || activeFile.path,
      indexed: false,
    }

    const targetDoc = doc ?? fallbackDoc
    if (activeFile.type === 'pdf') {
      setSelectedPdf(targetDoc)
    } else if (activeFile.type === 'markdown') {
      setSelectedMarkdown(targetDoc)
    }

    setActiveFile(null)
  }, [activeFile, docs, isLoading, setActiveFile])

  const handleCloseFile = () => {
    setSelectedPdf(null)
    setSelectedMarkdown(null)
    loadDocs()
  }

  const handleMoldetScan = async () => {
    if (!projectRoot) {
      setError(t('project.noProjectRoot'))
      return
    }
    const pdfDocs = docs.filter(d => d.doc_type === 'pdf')
    if (pdfDocs.length === 0) {
      showToast(t('project.noPdfFiles'), 'info')
      return
    }
    setIsMoldetScanning(true)
    setMoldetResult(null)
    setMoldetProgress({ current: 0, total: pdfDocs.length })
    setError('')
    try {
      const resp = await batchQuickMoldetScan(projectRoot, pdfDocs.map(d => d.doc_id))
      const withMolecules = resp.results.filter(r => r.pages_with_molecules.length > 0).length
      setMoldetResult({ scanned: resp.processed, withMolecules })
      if (resp.errors.length > 0) {
        console.warn('MoldDet scan errors:', resp.errors)
      }
      loadDocs()
      showToast(
        t('project.quickScanComplete', { processed: resp.processed, withMolecules }),
        resp.errors.length > 0 ? 'warning' : 'success',
      )
    } catch (e) {
      const msg = String(e)
      console.error('[ProjectView] MoldDet scan error:', msg)
      setError(t('project.molScanFailedDetail', { error: msg }))
      showToast(t('project.molScanFailed'), 'error')
    } finally {
      setIsMoldetScanning(false)
      setMoldetProgress(null)
    }
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
      isSyncing={isSyncing}
      syncStage={syncStage}
      indexProgress={indexProgress}
      indexResult={indexResult}
      isMoldetScanning={isMoldetScanning}
      moldetProgress={moldetProgress}
      moldetResult={moldetResult}
      error={error}
      scanWarnings={scanWarnings}
      moleculeStats={moleculeStats}
      onSync={handleSync}
      onMoldetScan={handleMoldetScan}
      onOpenFile={handleOpenFile}
      onDismissError={() => setError('')}
      onDismissWarnings={() => setScanWarnings([])}
      onRefreshDocs={loadDocs}
    />
  )
}
