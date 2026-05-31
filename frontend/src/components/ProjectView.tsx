import { useState, useEffect, useCallback } from 'react'
import { listProjectDocuments, scanProjectFiles, indexProjectRust, type IndexResult } from '../api/tauri-bridge'
import { extractPage } from '../api/moldet'
import { listen } from '@tauri-apps/api/event'
import { FolderIcon, FileTextIcon, FlaskIcon, ExternalLinkIcon, SettingsIcon, ArrowLeftIcon, SearchIcon } from './icons'
import type { DocumentEntry, ExtractionResult } from '../types'
import { getProjectRoot } from '../hooks/useProjectRoot'
import { showToast } from '../hooks/useToast'
import ErrorBanner from './ErrorBanner'
import { motion } from 'framer-motion'
import { StaggerContainer, StaggerItem } from './animations/StaggerContainer'
import PdfCanvas from './PdfCanvas'
import MoleculeOverlay from './MoleculeOverlay'
import MarkdownViewer from './MarkdownViewer'

import PageContainer from '../components/ui/PageContainer'
import PageTitle from '../components/ui/PageTitle'
import SectionTitle from '../components/ui/SectionTitle'
import Card from '../components/ui/Card'
import HoverCard from '../components/ui/HoverCard'
import CardGrid from '../components/ui/CardGrid'
import IconContainer from '../components/ui/IconContainer'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import BodyText from '../components/ui/BodyText'
import Caption from '../components/ui/Caption'
import Skeleton from '../components/ui/Skeleton'
import EmptyState from '../components/ui/EmptyState'
import Toolbar from '../components/ui/Toolbar'
import IconButton from '../components/ui/IconButton'

export default function ProjectView() {
  const [projectRoot, setProjectRoot] = useState(getProjectRoot())
  const [docs, setDocs] = useState<DocumentEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isIndexing, setIsIndexing] = useState(false)
  const [indexProgress, setIndexProgress] = useState<{ file: string; current: number; total: number } | null>(null)
  const [indexResult, setIndexResult] = useState<{ indexed: number; sections: number } | null>(null)
  const [error, setError] = useState('')

  // 文件查看状态
  const [selectedPdf, setSelectedPdf] = useState<DocumentEntry | null>(null)
  const [selectedMarkdown, setSelectedMarkdown] = useState<DocumentEntry | null>(null)
  // PDF 视图模式
  const [pdfViewMode, setPdfViewMode] = useState<'read' | 'detect'>('read')
  // 分子检测状态
  const [currentPage, setCurrentPage] = useState(1)
  const [pageDetections, setPageDetections] = useState<Map<number, ExtractionResult[]>>(new Map())
  const [isDetecting, setIsDetecting] = useState(false)
  const [selectedDetection, setSelectedDetection] = useState<number | null>(null)
  // 页面尺寸信息（由 PdfCanvas 回调提供）
  const [pageInfo, setPageInfo] = useState<{
    width: number; height: number; originalWidth: number; originalHeight: number; scale: number
  } | null>(null)
  // 当前页面的 data URL（发送给 MolDet）
  const [currentPageDataUrl, setCurrentPageDataUrl] = useState<string | null>(null)

  const loadDocs = async () => {
    const root = getProjectRoot()
    if (!root) return
    setIsLoading(true)
    setError('')
    try {
      const resp = await listProjectDocuments(root)
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
    setProjectRoot(getProjectRoot())
    loadDocs()
  }, [])

  const handleScan = async () => {
    const root = getProjectRoot()
    if (!root) return
    setIsLoading(true)
    setError('')
    try {
      const resp = await scanProjectFiles(root)
      if (resp.documents) {
        setDocs(resp.documents)
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
    scanProjectFiles(root).then(scanResp => {
      if (scanResp.documents) setDocs(scanResp.documents)
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
      listProjectDocuments(root).then(r => { if (r.documents) setDocs(r.documents) })
    } catch (e) {
      setError(String(e))
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
    setPdfViewMode('read')
    setPageDetections(new Map())
    setSelectedDetection(null)
  }

  // ---- 分子检测 ----
  const handleDetectPage = useCallback(async () => {
    if (!currentPageDataUrl || !pageInfo) return
    // 如果当前页已经检测过，跳过
    if (pageDetections.has(currentPage)) {
      showToast(`第 ${currentPage} 页已检测`, 'info')
      return
    }
    setIsDetecting(true)
    setSelectedDetection(null)
    try {
      // 将 data URL 转为 base64（去掉 data:image/png;base64, 前缀）
      const base64 = currentPageDataUrl.split(',')[1] || ''
      const resp = await extractPage(
        base64,
        currentPage - 1, // 后端 0-indexed
        pageInfo.originalWidth,
        pageInfo.originalHeight,
        pageInfo.width,
        pageInfo.height,
      )
      setPageDetections(prev => {
        const next = new Map(prev)
        next.set(currentPage, resp.results)
        return next
      })
      if (resp.results.length > 0) {
        showToast(`检测到 ${resp.results.length} 个分子`, 'success')
      } else {
        showToast('未检测到分子', 'info')
      }
    } catch (e) {
      console.error('Detection failed:', e)
      showToast('检测失败: ' + (e instanceof Error ? e.message : String(e)), 'error')
    } finally {
      setIsDetecting(false)
    }
  }, [currentPageDataUrl, pageInfo, currentPage, pageDetections])

  const projectName = projectRoot ? projectRoot.split('/').pop() || projectRoot : '未选择项目'

  // 稳定的 PdfCanvas 回调（阻断 re-render cascade）
  const handlePageRendered = useCallback((info: {
    pageNumber: number; width: number; height: number
    originalWidth: number; originalHeight: number; scale: number
  }) => { setPageInfo(info) }, [])

  const handleImageReady = useCallback((_num: number, dataUrl: string) => {
    setCurrentPageDataUrl(dataUrl)
  }, [])

  // PDF 视图
  if (selectedPdf) {
    const pdfUrl = `/api/v1/file/pdf?path=${encodeURIComponent(selectedPdf.path)}`
    const currentDetections = pageDetections.get(currentPage) || []
    const isDetectMode = pdfViewMode === 'detect'

    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
        {/* 工具栏 */}
        <Toolbar style={{ justifyContent: 'flex-start', gap: '8px', height: '48px', padding: '0 16px' }}>
          <IconButton size={32} onClick={handleCloseFile}>
            <ArrowLeftIcon size={18} />
          </IconButton>
          <Caption truncate style={{ fontSize: '13px', fontWeight: 500, flex: 1 }}>
            {selectedPdf.title || selectedPdf.path}
          </Caption>
          {/* 模式切换 */}
          <div style={{ display: 'flex', gap: '2px', background: 'var(--bg-base)', borderRadius: '6px', padding: '2px' }}>
            <button
              style={{
                padding: '4px 12px', fontSize: '12px', borderRadius: '4px', border: 'none',
                background: !isDetectMode ? 'var(--bg-surface)' : 'transparent',
                color: !isDetectMode ? 'var(--text-primary)' : 'var(--text-muted)',
                cursor: 'pointer', fontWeight: !isDetectMode ? 600 : 400,
              }}
              onClick={() => setPdfViewMode('read')}
            >
              阅读
            </button>
            <button
              style={{
                padding: '4px 12px', fontSize: '12px', borderRadius: '4px', border: 'none',
                background: isDetectMode ? 'var(--bg-surface)' : 'transparent',
                color: isDetectMode ? 'var(--text-primary)' : 'var(--text-muted)',
                cursor: 'pointer', fontWeight: isDetectMode ? 600 : 400,
                display: 'flex', alignItems: 'center', gap: '4px',
              }}
              onClick={() => setPdfViewMode('detect')}
            >
              <SearchIcon size={12} /> 分子检测
            </button>
          </div>
          {/* 检测模式：翻页 + 检测按钮 */}
          {isDetectMode && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '8px' }}>
              <button
                className="btn btn-secondary"
                style={{ padding: '3px 8px', fontSize: '11px' }}
                onClick={() => { setCurrentPage(p => Math.max(1, p - 1)); setSelectedDetection(null) }}
                disabled={currentPage <= 1}
              >
                ←
              </button>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)', minWidth: '40px', textAlign: 'center' }}>
                {currentPage}
              </span>
              <button
                className="btn btn-secondary"
                style={{ padding: '3px 8px', fontSize: '11px' }}
                onClick={() => setCurrentPage(p => p + 1)}
              >
                →
              </button>
              <button
                className="btn btn-primary"
                style={{ padding: '4px 12px', fontSize: '11px', marginLeft: '4px' }}
                onClick={handleDetectPage}
                disabled={isDetecting || !currentPageDataUrl}
              >
                {isDetecting ? '检测中...' : '检测当前页'}
              </button>
              {currentDetections.length > 0 && (
                <span style={{
                  fontSize: '11px', color: 'var(--success)',
                  background: 'rgba(22,163,74,0.1)', padding: '2px 8px', borderRadius: '4px',
                }}>
                  {currentDetections.length} 个分子
                </span>
              )}
            </div>
          )}
        </Toolbar>

        {/* PDF 内容区域 — 统一使用 PdfCanvas（共享缓存，无 iframe 双重下载） */}
        <div style={{
          flex: 1, overflow: 'auto', background: isDetectMode ? 'var(--bg-base)' : '#525659',
          display: 'flex', justifyContent: 'center', padding: isDetectMode ? '20px' : '0',
        }}>
          <div style={{ position: 'relative', display: 'inline-block' }}>
            <PdfCanvas
              url={pdfUrl}
              pageNumber={currentPage}
              scale={isDetectMode ? 1.5 : 1.2}
              generateImage={isDetectMode}
              onPageRendered={handlePageRendered}
              onImageReady={handleImageReady}
              style={{
                background: '#fff',
                boxShadow: isDetectMode ? '0 2px 12px rgba(0,0,0,0.15)' : 'none',
              }}
            />
            {/* 分子检测叠加层 */}
            {isDetectMode && pageInfo && currentDetections.length > 0 && (
              <MoleculeOverlay
                detections={currentDetections}
                renderWidth={pageInfo.width}
                renderHeight={pageInfo.height}
                originalHeight={pageInfo.originalHeight}
                scale={pageInfo.scale}
                selectedIndex={selectedDetection ?? undefined}
                onSelect={setSelectedDetection}
              />
            )}
          </div>
        </div>

        {/* 检测详情面板 */}
        {isDetectMode && selectedDetection !== null && currentDetections[selectedDetection] && (
          <div style={{
            borderTop: '1px solid var(--border)',
            padding: '12px 16px',
            background: 'var(--bg-surface)',
            display: 'flex',
            gap: '16px',
            alignItems: 'flex-start',
          }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>
                分子 #{selectedDetection + 1}
              </div>
              <div style={{ fontSize: '11px', fontFamily: 'monospace', wordBreak: 'break-all', color: 'var(--text-secondary)' }}>
                {currentDetections[selectedDetection].esmiles}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '12px', fontSize: '11px', color: 'var(--text-muted)' }}>
              <span>检测: {Math.round(currentDetections[selectedDetection].moldet_conf * 100)}%</span>
              <span>识别: {Math.round(currentDetections[selectedDetection].scribe_conf * 100)}%</span>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                综合: {Math.round(currentDetections[selectedDetection].composite_conf * 100)}%
              </span>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Markdown 视图
  if (selectedMarkdown) {
    return (
      <MarkdownViewer
        filePath={selectedMarkdown.path}
        onClose={handleCloseFile}
      />
    )
  }

  // 项目视图
  return (
    <PageContainer>
      {error && <ErrorBanner message={error} onDismiss={() => setError('')} />}

      {/* 头部 */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '32px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <IconContainer size={48}>
            <FolderIcon size={24} />
          </IconContainer>
          <div>
            <PageTitle style={{ marginBottom: '4px' }}>{projectName}</PageTitle>
            <BodyText muted size="sm">{projectRoot || '请先打开或创建一个项目'}</BodyText>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button
            variant="secondary"
            size="md"
            icon={<ExternalLinkIcon size={14} />}
            onClick={handleScan}
            disabled={!projectRoot || isLoading || isIndexing}
            loading={isLoading}
          >
            {isLoading ? '扫描中...' : '扫描文件'}
          </Button>
          <Button
            variant="secondary"
            size="md"
            icon={<FlaskIcon size={14} />}
            onClick={handleIndex}
            disabled={!projectRoot || isLoading || isIndexing}
            loading={isIndexing}
          >
            {isIndexing ? '索引中...' : '索引文件'}
          </Button>
          <Button
            variant="secondary"
            size="md"
            icon={<SettingsIcon size={14} />}
          >
            项目设置
          </Button>
        </div>
      </div>

      {/* 统计卡片 */}
      <StaggerContainer stagger={0.08}>
        <CardGrid style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginBottom: '32px' }}>
          <StaggerItem>
            <Card>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ color: 'var(--text-muted)' }}><FileTextIcon size={18} /></div>
                <div>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>{String(docs.length)}</div>
                  <Caption>文献</Caption>
                </div>
              </div>
            </Card>
          </StaggerItem>
          <StaggerItem>
            <Card>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ color: 'var(--text-muted)' }}><FlaskIcon size={18} /></div>
                <div>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>{indexResult ? String(indexResult.sections) : '—'}</div>
                  <Caption>Sections</Caption>
                </div>
              </div>
            </Card>
          </StaggerItem>
          <StaggerItem>
            <Card>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ color: 'var(--text-muted)' }}><FileTextIcon size={18} /></div>
                <div>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>{String(docs.filter(d => d.indexed).length)}</div>
                  <Caption>已索引</Caption>
                </div>
              </div>
            </Card>
          </StaggerItem>
          <StaggerItem>
            <Card>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ color: 'var(--text-muted)' }}><FolderIcon size={18} /></div>
                <div>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>{String(docs.length)}</div>
                  <Caption>文件</Caption>
                </div>
              </div>
            </Card>
          </StaggerItem>
        </CardGrid>
      </StaggerContainer>

      {/* 索引进度条 */}
      {isIndexing && indexProgress && (
        <Card padding="14px 18px" style={{ marginBottom: '16px', borderRadius: '10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <BodyText size="sm" style={{ fontWeight: 500 }}>
              正在索引 {indexProgress.current}/{indexProgress.total}
            </BodyText>
            <Caption truncate style={{ maxWidth: '300px' }}>
              {indexProgress.file}
            </Caption>
          </div>
          <div className="download-progress-bar">
            <motion.div
              className="download-progress-fill shimmer"
              style={{ width: `${Math.round(indexProgress.current * 100 / indexProgress.total)}%` }}
              animate={{ backgroundPosition: ['0% 0%', '100% 0%'] }}
              transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
            />
          </div>
        </Card>
      )}

      {indexResult && indexResult.indexed > 0 && (
        <Card padding="12px 16px" style={{ marginBottom: '16px', borderRadius: '8px', background: 'rgba(22,163,74,0.1)', borderColor: 'rgba(22,163,74,0.3)' }}>
          <BodyText size="sm" style={{ color: '#16a34a' }}>
            已索引 {indexResult.indexed} 个 PDF，生成 {indexResult.sections} 个 section
          </BodyText>
        </Card>
      )}

      {/* 文件列表 */}
      <SectionTitle style={{ fontSize: '16px', textTransform: 'none', letterSpacing: 'normal', marginBottom: '16px' }}>
        项目文件
      </SectionTitle>

      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <Skeleton variant="row" count={5} height={48} />
        </div>
      ) : docs.length === 0 ? (
        <EmptyState
          message={projectRoot ? '暂无文件，点击"扫描文件"索引项目内容' : '请先打开或创建一个项目'}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {docs.map((doc, index) => (
            <motion.div
              key={doc.doc_id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.03, duration: 0.3 }}
            >
              <HoverCard
                onClick={() => handleOpenFile(doc)}
                style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 16px', borderRadius: '8px' }}
              >
                <FileTextIcon size={16} />
                <BodyText size="md" style={{ flex: 1 }}>{doc.title || doc.path}</BodyText>
                <Badge variant="neutral">{doc.doc_type}</Badge>
                {doc.indexed ? (
                  <Badge variant="success">已索引</Badge>
                ) : (
                  <Badge variant="neutral">未索引</Badge>
                )}
              </HoverCard>
            </motion.div>
          ))}
        </div>
      )}
    </PageContainer>
  )
}
