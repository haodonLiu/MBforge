import { useState, useCallback, useMemo } from 'react'
import { convertFileSrc } from '@tauri-apps/api/core'
import { extractPage } from '../../api/moldet'
import { parsePdf, type ImageRef, getDocumentOcrLayout, type OcrBlock } from '../../api/tauri/pdf'
import { showToast } from '../../hooks/useToast'
import { extractRoiText } from '../../utils/roiText'
import type { DocumentEntry, ExtractionResult } from '../../types'
import PdfCanvas from '../PdfCanvas'
import MoleculeOverlay from '../MoleculeOverlay'
import OcrOverlay from '../OcrOverlay'
import MoleculeDetailPanel from '../molecule/MoleculeDetailPanel'
import OcrResultPanel from '../OcrResultPanel'
import Toolbar from '../ui/Toolbar'
import IconButton from '../ui/IconButton'
import Caption from '../ui/Caption'
import { ArrowLeftIcon, SearchIcon } from '../icons'

interface Props {
  doc: DocumentEntry
  projectRoot: string
  onClose: () => void
}

export default function PdfViewer({ doc, projectRoot, onClose }: Props) {
  const [pdfViewMode, setPdfViewMode] = useState<'read' | 'detect' | 'ocr'>('read')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageDetections, setPageDetections] = useState<Map<number, ExtractionResult[]>>(new Map())
  const [isDetecting, setIsDetecting] = useState(false)
  const [selectedDetection, setSelectedDetection] = useState<number | null>(null)
  const [pageInfo, setPageInfo] = useState<{
    width: number; height: number; originalWidth: number; originalHeight: number; scale: number
  } | null>(null)
  const [currentPageDataUrl, setCurrentPageDataUrl] = useState<string | null>(null)
  const [pdfScale, setPdfScale] = useState(1.5)
  const [showTextLayer, setShowTextLayer] = useState(true)
  const [pageTextItems, setPageTextItems] = useState<Map<number, { str: string; x: number; y: number; width: number; height: number }[]>>(new Map())
  const [pdfOcrSummary, setPdfOcrSummary] = useState<{ totalChars: number; textDensity: string } | null>(null)
  const [pageJumpInput, setPageJumpInput] = useState('')
  const [showTextPanel, setShowTextPanel] = useState(false)
  const [pdfPageCount, setPdfPageCount] = useState(0)
  const [showImagePanel, setShowImagePanel] = useState(false)
  const [extractedImages, setExtractedImages] = useState<ImageRef[]>([])
  const [isLoadingImages, setIsLoadingImages] = useState(false)

  // OCR 可视化状态
  const [ocrBlocks, setOcrBlocks] = useState<OcrBlock[]>([])
  const [showOcrPanel, setShowOcrPanel] = useState(false)
  const [selectedOcrIndex, setSelectedOcrIndex] = useState<number | null>(null)
  const [hoveredOcrIndex, setHoveredOcrIndex] = useState<number | null>(null)
  const [isLoadingOcr, setIsLoadingOcr] = useState(false)

  const currentDetections = pageDetections.get(currentPage) || []
  const isDetectMode = pdfViewMode === 'detect'
  const isOcrMode = pdfViewMode === 'ocr'
  const currentTextItems = pageTextItems.get(currentPage) || []
  const currentTextTotal = currentTextItems.reduce((s, i) => s + i.str.length, 0)
  const hasTextLayer = currentTextTotal > 10

  const pdfUrl = useMemo(() => {
    const root = projectRoot
    if (!root) return ''
    const absPath = doc.path.includes(':') || doc.path.startsWith('/')
      ? doc.path
      : `${root.replace(/\\$/,'')}\\${doc.path.replace(/\//g,'\\')}`
    try {
      return convertFileSrc(absPath)
    } catch {
      return `/api/v1/file/pdf?path=${encodeURIComponent(absPath)}&project_root=${encodeURIComponent(root)}`
    }
  }, [doc.path, projectRoot])

  const handleDetectPage = useCallback(async () => {
    if (!currentPageDataUrl || !pageInfo) return
    if (pageDetections.has(currentPage)) {
      showToast(`第 ${currentPage} 页已检测`, 'info')
      return
    }
    setIsDetecting(true)
    setSelectedDetection(null)
    try {
      const base64 = currentPageDataUrl.split(',')[1] || ''
      const resp = await extractPage(
        base64,
        currentPage - 1,
        pageInfo.originalWidth,
        pageInfo.originalHeight,
        pageInfo.width,
        pageInfo.height,
      )
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

  // 保存编辑后的分子
  const handleSaveMolecule = useCallback((newSmiles: string) => {
    if (selectedDetection === null) return
    setPageDetections(prev => {
      const next = new Map(prev)
      const detections = next.get(currentPage) || []
      const updated = [...detections]
      updated[selectedDetection] = {
        ...updated[selectedDetection],
        esmiles: newSmiles,
      }
      next.set(currentPage, updated)
      return next
    })
    showToast('分子已更新', 'success')
  }, [selectedDetection, currentPage])

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

  const handleLoadImages = useCallback(async () => {
    if (extractedImages.length > 0) {
      setShowImagePanel(true)
      return
    }
    setIsLoadingImages(true)
    try {
      const result = await parsePdf(doc.path, 512, 128, 'pdf_inspector')
      setExtractedImages(result.images || [])
      setShowImagePanel(true)
    } catch (e) {
      console.error('Failed to load images:', e)
      showToast('图片提取失败', 'error')
    } finally {
      setIsLoadingImages(false)
    }
  }, [doc.path, extractedImages.length])

  const handleLoadOcr = useCallback(async () => {
    if (ocrBlocks.length > 0) {
      setShowOcrPanel(true)
      return
    }
    setIsLoadingOcr(true)
    try {
      const result = await getDocumentOcrLayout(doc.path)
      setOcrBlocks(result.blocks || [])
      setShowOcrPanel(true)
      if (result.blocks.length > 0) {
        showToast(`加载 ${result.blocks.length} 个 OCR 块`, 'success')
      } else {
        showToast('未找到 OCR 布局数据', 'info')
      }
    } catch (e) {
      console.error('Failed to load OCR layout:', e)
      showToast('OCR 布局加载失败', 'error')
    } finally {
      setIsLoadingOcr(false)
    }
  }, [doc.path, ocrBlocks.length])

  const resolveImageUrl = useCallback((img: ImageRef): string => {
    if (img.rel_path) {
      const absPath = `${projectRoot.replace(/\\$/,'')}\\${img.rel_path.replace(/\//g,'\\')}`
      try {
        return convertFileSrc(absPath)
      } catch {
        return ''
      }
    }
    return ''
  }, [projectRoot])

  const handleJumpToPage = useCallback(() => {
    const n = parseInt(pageJumpInput, 10)
    if (n > 0 && n <= (pageInfo ? 10000 : n)) {
      setCurrentPage(n)
      setSelectedDetection(null)
      setPageJumpInput('')
    }
  }, [pageJumpInput, pageInfo])

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* 工具栏 */}
      <Toolbar style={{ justifyContent: 'flex-start', gap: '8px', height: '48px', padding: '0 16px' }}>
        <IconButton size={32} onClick={onClose}>
          <ArrowLeftIcon size={18} />
        </IconButton>
        <Caption truncate style={{ fontSize: '13px', fontWeight: 500, flex: 1 }}>
          {doc.title || doc.path}
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
              background: pdfViewMode === 'read' ? 'var(--bg-surface)' : 'transparent',
              color: pdfViewMode === 'read' ? 'var(--text-primary)' : 'var(--text-muted)',
              cursor: 'pointer', fontWeight: pdfViewMode === 'read' ? 600 : 400,
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
          <button
            style={{
              padding: '4px 10px', fontSize: '11px', borderRadius: '4px', border: 'none',
              background: isOcrMode ? 'var(--bg-surface)' : 'transparent',
              color: isOcrMode ? 'var(--text-primary)' : 'var(--text-muted)',
              cursor: 'pointer', fontWeight: isOcrMode ? 600 : 400,
            }}
            onClick={() => {
              if (!isOcrMode) {
                setPdfViewMode('ocr')
                handleLoadOcr()
              } else {
                setPdfViewMode('read')
              }
            }}
            disabled={isLoadingOcr}
          >
            {isLoadingOcr ? '加载中...' : 'OCR'}
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

        {/* 图片提取按钮 */}
        <button
          onClick={handleLoadImages}
          disabled={isLoadingImages}
          style={{
            padding: '4px 8px', fontSize: '11px', borderRadius: '4px', border: '1px solid var(--border)',
            background: showImagePanel ? 'var(--bg-surface)' : 'transparent',
            color: 'var(--text-muted)', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: '4px',
            opacity: isLoadingImages ? 0.5 : 1,
          }}
          title={isLoadingImages ? '提取中...' : (showImagePanel ? '关闭图片面板' : '提取图片')}
        >
          🖼️{extractedImages.length > 0 ? ` ${extractedImages.length}` : ''}
        </button>

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
          background: isDetectMode || isOcrMode ? 'var(--bg-base)' : '#525659',
          display: 'flex', justifyContent: 'center', padding: isDetectMode || isOcrMode ? '20px' : '0',
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
            {isOcrMode && pageInfo && ocrBlocks.length > 0 && (
              <OcrOverlay
                blocks={ocrBlocks}
                renderWidth={pageInfo.width}
                renderHeight={pageInfo.height}
                originalHeight={pageInfo.originalHeight}
                scale={pageInfo.scale}
                page={currentPage}
                selectedIndex={selectedOcrIndex ?? undefined}
                onSelect={setSelectedOcrIndex}
                onHover={setHoveredOcrIndex}
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

        {/* OCR 结果面板 */}
        {showOcrPanel && (
          <OcrResultPanel
            blocks={ocrBlocks}
            currentPage={currentPage}
            selectedIndex={selectedOcrIndex}
            hoveredIndex={hoveredOcrIndex}
            onSelect={setSelectedOcrIndex}
            onClose={() => setShowOcrPanel(false)}
          />
        )}

        {/* 图片面板（提取图片 + VLM 描述） */}
        {showImagePanel && (
          <div style={{
            width: '300px', borderLeft: '1px solid var(--border)',
            background: 'var(--bg-surface)', display: 'flex', flexDirection: 'column',
            overflow: 'hidden', flexShrink: 0,
          }}>
            <div style={{
              padding: '8px 12px', borderBottom: '1px solid var(--border)',
              fontSize: '11px', fontWeight: 600, display: 'flex',
              justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span>提取图片 ({extractedImages.length})</span>
              <button
                onClick={() => setShowImagePanel(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--text-muted)', fontSize: '14px', lineHeight: 1 }}
              >✕</button>
            </div>
            <div style={{
              flex: 1, overflow: 'auto', padding: '12px',
              display: 'flex', flexDirection: 'column', gap: '12px',
            }}>
              {extractedImages.length === 0 && (
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  {isLoadingImages ? '提取中...' : '未提取到图片'}
                </span>
              )}
              {extractedImages.map((img, idx) => {
                const imgUrl = resolveImageUrl(img)
                return (
                  <div key={idx} style={{
                    border: '1px solid var(--border)',
                    borderRadius: '6px', overflow: 'hidden',
                    background: 'var(--bg-base)',
                  }}>
                    {imgUrl && (
                      <img
                        src={imgUrl}
                        alt={img.filename}
                        style={{ width: '100%', height: 'auto', display: 'block' }}
                        loading="lazy"
                      />
                    )}
                    <div style={{ padding: '8px 10px' }}>
                      <div style={{
                        fontSize: '10px', color: 'var(--text-muted)',
                        marginBottom: '4px', display: 'flex', justifyContent: 'space-between',
                      }}>
                        <span>第 {img.page} 页</span>
                        {img.esmiles && (
                          <span style={{
                            fontFamily: 'monospace', color: 'var(--success)',
                            fontSize: '9px',
                          }}>✓ SMILES</span>
                        )}
                      </div>
                      {img.description && (
                        <div style={{
                          fontSize: '11px', color: 'var(--text-secondary)',
                          lineHeight: 1.5,
                        }}>
                          {img.description}
                        </div>
                      )}
                      {!img.description && !img.esmiles && (
                        <div style={{
                          fontSize: '10px', color: 'var(--text-muted)', fontStyle: 'italic',
                        }}>
                          暂无描述
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* 检测详情面板 */}
      {isDetectMode && selectedDetection !== null && currentDetections[selectedDetection] && (
        <MoleculeDetailPanel
          detection={currentDetections[selectedDetection]}
          index={selectedDetection}
          onSave={handleSaveMolecule}
        />
      )}
    </div>
  )
}
