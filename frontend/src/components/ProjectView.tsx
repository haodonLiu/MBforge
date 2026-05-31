import { useState, useEffect, useCallback, useMemo } from 'react'
import { listProjectDocuments, scanProjectFiles, indexProjectRust, type IndexResult } from '../api/tauri-bridge'
import { extractPage } from '../api/moldet'
import { listen } from '@tauri-apps/api/event'
import { convertFileSrc } from '@tauri-apps/api/core'
import { FolderIcon, FileTextIcon, FlaskIcon, ExternalLinkIcon, SettingsIcon, ArrowLeftIcon, SearchIcon } from './icons'
import type { DocumentEntry, ExtractionResult } from '../types'
import { extractRoiText } from '../utils/roiText'
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
  // PDF 缩放控制
  const [pdfScale, setPdfScale] = useState(1.5)
  // 文本层开关
  const [showTextLayer, setShowTextLayer] = useState(true)
  // 每页文本内容（由 PdfCanvas 回调填充）
  const [pageTextItems, setPageTextItems] = useState<Map<number, { str: string; x: number; y: number; width: number; height: number }[]>>(new Map())
  // OCR 状态摘要
  const [pdfOcrSummary, setPdfOcrSummary] = useState<{ totalChars: number; textDensity: string } | null>(null)
  // 跳转页码输入
  const [pageJumpInput, setPageJumpInput] = useState('')
  // 文本面板开关
  const [showTextPanel, setShowTextPanel] = useState(false)
  // PDF 总页数
  const [pdfPageCount, setPdfPageCount] = useState(0)

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
    console.log('[ProjectView] handleScan, root:', JSON.stringify(root))
    if (!root) {
      console.warn('[ProjectView] No project root, cannot scan')
      setError('项目根路径未设置，请先打开一个项目')
      return
    }
    setIsLoading(true)
    setError('')
    try {
      const resp = await scanProjectFiles(root)
      console.log('[ProjectView] scan response:', JSON.stringify(resp))
      if (resp.documents) {
        if (resp.documents.length === 0) {
          console.log('[ProjectView] No documents found')
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
      // ROI 文本提取：为每个检测结果填充 context_text
      const textItems = pageTextItems.get(currentPage) || []
      const enriched = resp.results.map(r => {
        if (r.bbox_pdf && textItems.length > 0 && !r.context_text) {
          const ctx = extractRoiText(r.bbox_pdf, textItems, pageInfo.originalHeight)
          return { ...r, context_text: ctx }
        }
        return r
      })
      setPageDetections(prev => {
        const next = new Map(prev)
        next.set(currentPage, enriched)
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

  const handlePageCount = useCallback((count: number) => {
    setPdfPageCount(count)
  }, [])

  const handleTextContent = useCallback((_page: number, items: { str: string; x: number; y: number; width: number; height: number }[]) => {
    setPageTextItems(prev => {
      const next = new Map(prev)
      next.set(_page, items)
      return next
    })
    const totalChars = items.reduce((s, i) => s + i.str.length, 0)
    if (totalChars > 10) {
      setPdfOcrSummary(prev => ({
        totalChars: (prev?.totalChars ?? 0) + totalChars,
        textDensity: totalChars > 500 ? 'rich' : totalChars > 100 ? 'medium' : 'sparse',
      }))
    }
  }, [])

  const handleZoomIn = useCallback(() => {
    setPdfScale(s => Math.min(s + 0.3, 5))
  }, [])

  const handleZoomOut = useCallback(() => {
    setPdfScale(s => Math.max(s - 0.3, 0.5))
  }, [])

  const handleZoomReset = useCallback(() => {
    setPdfScale(1.5)
  }, [])

  const handleJumpToPage = useCallback(() => {
    const n = parseInt(pageJumpInput, 10)
    if (n > 0 && n <= (pageInfo ? 10000 : n)) {
      setCurrentPage(n)
      setSelectedDetection(null)
      setPageJumpInput('')
    }
  }, [pageJumpInput, pageInfo])

  // PDF URL（将相对路径转为 Tauri asset URL）
  const pdfUrl = useMemo(() => {
    if (!selectedPdf) return ''
    const root = getProjectRoot()
    if (!root) return ''
    const absPath = selectedPdf.path.includes(':') || selectedPdf.path.startsWith('/')
      ? selectedPdf.path
      : `${root.replace(/\\$/,'')}\\${selectedPdf.path.replace(/\//g,'\\')}`
    try {
      return convertFileSrc(absPath)
    } catch {
      return `/api/v1/file/pdf?path=${encodeURIComponent(absPath)}`
    }
  }, [selectedPdf?.path])

  // PDF 视图
  if (selectedPdf) {
    const currentDetections = pageDetections.get(currentPage) || []
    const isDetectMode = pdfViewMode === 'detect'
    const currentTextItems = pageTextItems.get(currentPage) || []
    const currentTextTotal = currentTextItems.reduce((s, i) => s + i.str.length, 0)
    const hasTextLayer = currentTextTotal > 10

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

          {/* 缩放控制 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
            <IconButton size={28} onClick={handleZoomOut} title="缩小">
              <span style={{ fontSize: '14px', lineHeight: 1 }}>－</span>
            </IconButton>
            <button
              onClick={handleZoomReset}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: '11px', color: 'var(--text-muted)', padding: '2px 6px',
                fontFamily: 'monospace',
              }}
              title="重置缩放"
            >
              {Math.round(pdfScale * 100)}%
            </button>
            <IconButton size={28} onClick={handleZoomIn} title="放大">
              <span style={{ fontSize: '14px', lineHeight: 1 }}>＋</span>
            </IconButton>
          </div>

          {/* 分页跳转 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <button
              className="btn btn-secondary"
              style={{ padding: '3px 6px', fontSize: '11px' }}
              onClick={() => { setCurrentPage(p => Math.max(1, p - 1)); setSelectedDetection(null) }}
              disabled={currentPage <= 1}
            >←</button>
            <input
              type="text"
              value={pageJumpInput || currentPage}
              onChange={e => setPageJumpInput(e.target.value.replace(/\D/g, ''))}
              onKeyDown={e => { if (e.key === 'Enter') handleJumpToPage() }}
              onBlur={() => setPageJumpInput('')}
              style={{
                width: '36px', textAlign: 'center', fontSize: '11px',
                border: '1px solid var(--border)', borderRadius: '4px',
                background: 'var(--bg-base)', color: 'var(--text-primary)',
                padding: '2px 4px', fontFamily: 'monospace', outline: 'none',
              }}
            />
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              / {pdfPageCount || '?'}
            </span>
            <button
              className="btn btn-secondary"
              style={{ padding: '3px 6px', fontSize: '11px' }}
              onClick={() => setCurrentPage(p => p + 1)}
            >→</button>
          </div>

          {/* 模式切换 */}
          <div style={{ display: 'flex', gap: '2px', background: 'var(--bg-base)', borderRadius: '6px', padding: '2px' }}>
            <button
              style={{
                padding: '4px 10px', fontSize: '11px', borderRadius: '4px', border: 'none',
                background: !isDetectMode ? 'var(--bg-surface)' : 'transparent',
                color: !isDetectMode ? 'var(--text-primary)' : 'var(--text-muted)',
                cursor: 'pointer', fontWeight: !isDetectMode ? 600 : 400,
              }}
              onClick={() => setPdfViewMode('read')}
            >阅读</button>
            <button
              style={{
                padding: '4px 10px', fontSize: '11px', borderRadius: '4px', border: 'none',
                background: isDetectMode ? 'var(--bg-surface)' : 'transparent',
                color: isDetectMode ? 'var(--text-primary)' : 'var(--text-muted)',
                cursor: 'pointer', fontWeight: isDetectMode ? 600 : 400,
                display: 'flex', alignItems: 'center', gap: '4px',
              }}
              onClick={() => setPdfViewMode('detect')}
            >
              <SearchIcon size={11} /> 分子
            </button>
          </div>

          {/* 文本层开关 + 文本侧栏 */}
          <button
            onClick={() => setShowTextLayer(!showTextLayer)}
            style={{
              padding: '4px 8px', fontSize: '11px', borderRadius: '4px', border: '1px solid var(--border)',
              background: showTextLayer ? 'var(--bg-surface)' : 'transparent',
              color: 'var(--text-muted)', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '4px',
              opacity: hasTextLayer ? 1 : 0.4,
            }}
            disabled={!hasTextLayer}
            title={hasTextLayer ? (showTextLayer ? '隐藏文本层' : '显示文本层') : '此页无文本内容'}
          >
            T{hasTextLayer ? ' ✓' : ''}
          </button>
          {hasTextLayer && (
            <button
              onClick={() => setShowTextPanel(!showTextPanel)}
              style={{
                padding: '4px 8px', fontSize: '11px', borderRadius: '4px', border: '1px solid var(--border)',
                background: showTextPanel ? 'var(--bg-surface)' : 'transparent',
                color: 'var(--text-muted)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: '4px',
              }}
              title={showTextPanel ? '关闭文本侧栏' : '打开文本侧栏'}
            >
              ¶
            </button>
          )}

          {/* OCR 状态标识 */}
          {pdfOcrSummary && (
            <span style={{
              fontSize: '10px', color: 'var(--text-muted)',
              display: 'flex', alignItems: 'center', gap: '3px',
            }}>
              <span style={{
                width: '6px', height: '6px', borderRadius: '50%',
                background: pdfOcrSummary.textDensity === 'rich' ? 'var(--success)'
                  : pdfOcrSummary.textDensity === 'medium' ? 'var(--warning)' : 'var(--danger)',
              }} />
              {pdfOcrSummary.totalChars > 1000
                ? `${(pdfOcrSummary.totalChars / 1000).toFixed(1)}K chars`
                : `${pdfOcrSummary.totalChars} chars`}
            </span>
          )}

          {/* 检测模式：检测按钮 */}
          {isDetectMode && (
            <>
              <button
                className="btn btn-primary"
                style={{ padding: '4px 10px', fontSize: '11px' }}
                onClick={handleDetectPage}
                disabled={isDetecting || !currentPageDataUrl}
              >
                {isDetecting ? '检测中...' : '检测'}
              </button>
              {currentDetections.length > 0 && (
                <span style={{
                  fontSize: '10px', color: 'var(--success)',
                  background: 'rgba(22,163,74,0.1)', padding: '2px 6px', borderRadius: '4px',
                }}>
                  {currentDetections.length}个
                </span>
              )}
            </>
          )}
        </Toolbar>

        {/* 主区域 */}
        <div style={{
          flex: 1, display: 'flex', overflow: 'hidden',
        }}>
          {/* PDF 内容 */}
          <div style={{
            flex: 1, overflow: 'auto',
            background: isDetectMode ? 'var(--bg-base)' : '#525659',
            display: 'flex', justifyContent: 'center', padding: isDetectMode ? '20px' : '0',
          }}>
            <div style={{ position: 'relative', display: 'inline-block' }}>
              <PdfCanvas
                url={pdfUrl}
                pageNumber={currentPage}
                scale={pdfScale}
                generateImage={isDetectMode}
                showTextLayer={showTextLayer && hasTextLayer}
                onPageRendered={handlePageRendered}
                onImageReady={handleImageReady}
                onTextContent={handleTextContent}
                onPageCount={handlePageCount}
                style={{
                  background: '#fff',
                  boxShadow: isDetectMode ? '0 2px 12px rgba(0,0,0,0.15)' : 'none',
                }}
              />
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

          {/* 文本面板（OCR 侧栏） */}
          {showTextPanel && hasTextLayer && (
            <div style={{
              width: '280px', borderLeft: '1px solid var(--border)',
              background: 'var(--bg-surface)', display: 'flex', flexDirection: 'column',
              overflow: 'hidden', flexShrink: 0,
            }}>
              <div style={{
                padding: '8px 12px', borderBottom: '1px solid var(--border)',
                fontSize: '11px', fontWeight: 600, display: 'flex',
                justifyContent: 'space-between', alignItems: 'center',
              }}>
                <span>第 {currentPage} 页文本</span>
                <button
                  onClick={() => setShowTextPanel(false)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--text-muted)', fontSize: '14px', lineHeight: 1 }}
                >✕</button>
              </div>
              <div style={{
                flex: 1, overflow: 'auto', padding: '12px',
                fontSize: '11px', lineHeight: 1.6, color: 'var(--text-secondary)',
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>
                {currentTextItems.map(item => item.str).join(' ')}
              </div>
              <div style={{
                padding: '6px 12px', borderTop: '1px solid var(--border)',
                fontSize: '10px', color: 'var(--text-muted)',
                display: 'flex', justifyContent: 'space-between',
              }}>
                <span>{currentTextItems.length} 段</span>
                <span>{currentTextTotal} 字符</span>
              </div>
            </div>
          )}
        </div>

        {/* 检测详情面板 */}
        {isDetectMode && selectedDetection !== null && currentDetections[selectedDetection] && (
          <div style={{
            borderTop: '1px solid var(--border)',
            padding: '12px 16px',
            background: 'var(--bg-surface)',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}>
            <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>
                  分子 #{selectedDetection + 1}
                </div>
                <div style={{ fontSize: '11px', fontFamily: 'monospace', wordBreak: 'break-all', color: 'var(--text-secondary)' }}>
                  {currentDetections[selectedDetection].esmiles}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '12px', fontSize: '11px', color: 'var(--text-muted)', flexShrink: 0 }}>
                <span>检测: {Math.round(currentDetections[selectedDetection].moldet_conf * 100)}%</span>
                <span>识别: {Math.round(currentDetections[selectedDetection].scribe_conf * 100)}%</span>
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                  综合: {Math.round(currentDetections[selectedDetection].composite_conf * 100)}%
                </span>
              </div>
            </div>
            {/* 上下文文本（ROI 提取） */}
            {currentDetections[selectedDetection].context_text && (
              <div style={{
                fontSize: '11px', color: 'var(--text-secondary)',
                background: 'var(--bg-base)', padding: '8px 10px',
                borderRadius: '6px', border: '1px solid var(--border)',
                lineHeight: 1.5, maxHeight: '80px', overflow: 'auto',
              }}>
                <span style={{ fontWeight: 600, color: 'var(--text-muted)', marginRight: '6px' }}>上下文:</span>
                {currentDetections[selectedDetection].context_text}
              </div>
            )}
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
