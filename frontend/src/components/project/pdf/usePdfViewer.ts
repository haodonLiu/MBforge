import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { convertFileSrc } from '@tauri-apps/api/core'
import {
  detectPageMolecules,
  getCachedDetections,
  clearDocumentDetections,
  extractPdfImages,
  type ImageRef,
} from '../../../services/pdfService'
import { getDocumentOcrLayout } from '../../../api/tauri/pdf'
import { showToast } from '../../../hooks/useToast'
import { extractRoiText } from '../../../utils/roiText'
import type { DocumentEntry, ExtractionResult } from '../../../types'
import type { OcrBlock } from '../../../api/tauri/pdf'
import type { FigureLabel, CorefPrediction } from '../../../api/tauri/result_pane'
import { getFigureLabels, getCorefPredictions } from '../../../api/tauri/result_pane'

export function usePdfViewer(doc: DocumentEntry, projectRoot: string, initialMode?: 'read' | 'detect' | 'ocr' | 'coref') {
  const [pdfViewMode, setPdfViewMode] = useState(initialMode ?? 'read')
  const isDetectMode = pdfViewMode === 'detect'
  const isOcrMode = pdfViewMode === 'ocr'
  const isCorefMode = pdfViewMode === 'coref'
  const isSinglePageMode = isDetectMode || isOcrMode || isCorefMode

  // 置信度阈值（0-1）
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.3)

  const [currentPage, setCurrentPage] = useState(1)
  const [pageDetections, setPageDetections] = useState<Map<number, ExtractionResult[]>>(new Map())
  const [isDetecting, setIsDetecting] = useState(false)
  const [selectedDetection, setSelectedDetection] = useState<number | null>(null)
  const [pageInfo, setPageInfo] = useState<{
    pageNumber: number; width: number; height: number; originalWidth: number; originalHeight: number; scale: number
  } | null>(null)
  const pageInfoRef = useRef(pageInfo)
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

  const [ocrBlocks, setOcrBlocks] = useState<OcrBlock[]>([])
  const [showOcrPanel, setShowOcrPanel] = useState(false)
  const [selectedOcrIndex, setSelectedOcrIndex] = useState<number | null>(null)
  const [hoveredOcrIndex, setHoveredOcrIndex] = useState<number | null>(null)
  const [isLoadingOcr, setIsLoadingOcr] = useState(false)

  // Coref mode: 当前页 labels + predictions + 阈值
  const [corefThreshold, setCorefThreshold] = useState(0.3)
  const [corefLabelsByPage, setCorefLabelsByPage] = useState<Map<number, FigureLabel[]>>(new Map())
  const [corefPredictionsByPage, setCorefPredictionsByPage] = useState<Map<number, CorefPrediction[]>>(new Map())
  const [isLoadingCoref, setIsLoadingCoref] = useState(false)

  const [pdfUrl, setPdfUrl] = useState('')
  const [pdfLoading, setPdfLoading] = useState(true)
  const pdfScrollRef = useRef<HTMLDivElement>(null)
  const autoLoadOcrDone = useRef(false)
  const wheelSwitchAtRef = useRef(0)
  const WHEEL_SWITCH_COOLDOWN_MS = 200

  const getOcrEmptyHint = (parser: string) => {
    if (parser === 'pdf_inspector') {
      return '当前 PDF 为文字版，无需 OCR 布局'
    }
    if (parser.startsWith('mineru')) {
      return 'OCR 未返回布局块（MinerU Agent API 不提供 layout；使用 Precise API 可获取）'
    }
    return '未找到 OCR 布局数据'
  }

  const currentDetections = pageDetections.get(currentPage) || []
  const currentTextItems = pageTextItems.get(currentPage) || []
  const currentTextTotal = currentTextItems.reduce((s, i) => s + i.str.length, 0)
  const hasTextLayer = currentTextTotal > 10
  const canDetect = !!currentPageDataUrl && !!pageInfo

  const normalizePath = useCallback((p: string) => p.replace(/^\\\\\?\\/, '').replace(/^\?\//, '').replace(/\\/g, '/'), [])
  const absDocPath = useMemo(() => {
    const root = projectRoot
    if (!root) return doc.path
    const pdfPath = doc.source_path || doc.path
    return pdfPath.includes(':') || pdfPath.startsWith('/')
      ? normalizePath(pdfPath)
      : `${normalizePath(root).replace(/\/$/, '')}/${pdfPath.replace(/\\/g, '/')}`
  }, [doc.path, doc.source_path, projectRoot, normalizePath])

  useEffect(() => {
    let cancelled = false
    setPdfUrl('')
    setPdfLoading(true)
    const url = convertFileSrc(absDocPath, 'mbforge')
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!cancelled) { setPdfUrl(url); setPdfLoading(false) }
    return () => { cancelled = true }
  }, [absDocPath])

  useEffect(() => {
    if (initialMode === 'ocr' && !autoLoadOcrDone.current) {
      autoLoadOcrDone.current = true
      setIsLoadingOcr(true)
      getDocumentOcrLayout(absDocPath, doc.doc_id)
        .then(result => {
          setOcrBlocks(result.blocks)
          setShowOcrPanel(true)
          const hasBlocks = result.blocks.length > 0
          showToast(
            hasBlocks ? `加载 ${result.blocks.length} 个 OCR 块` : getOcrEmptyHint(result.parser),
            hasBlocks ? 'success' : 'info',
          )
        })
        .catch((e: unknown) => {
          console.error('Failed to load OCR layout:', e)
          const msg = e instanceof Error ? e.message : String(e)
          showToast(`OCR 布局加载失败：${msg}`, 'error')
        })
        .finally(() => setIsLoadingOcr(false))
    }
  }, [absDocPath, doc.doc_id, initialMode])

  const enrichResults = useCallback((results: ExtractionResult[], pageNum: number) => {
    const textItems = pageTextItems.get(pageNum) || []
    const info = pageInfoRef.current
    if (!info) return results
    return results.map(r => {
      if (r.bbox_pdf && textItems.length > 0 && !r.context_text) {
        return { ...r, context_text: extractRoiText(r.bbox_pdf, textItems, info.originalHeight) }
      }
      return r
    })
  }, [pageTextItems])

  const loadCachedDetections = useCallback(async (pageNum: number): Promise<boolean> => {
    if (!projectRoot) return false
    try {
      const result = await getCachedDetections({
        projectRoot,
        docId: doc.doc_id,
        page: pageNum,
      })
      if (result.success && result.data && result.data.count > 0) {
        const enriched = enrichResults(result.data.results, pageNum)
        setPageDetections(prev => { const next = new Map(prev); next.set(pageNum, enriched); return next })
        return true
      }
    } catch (e) {
      console.warn('Failed to load cached detections:', e)
    }
    return false
  }, [projectRoot, doc.doc_id, enrichResults])

  const handleDetectPage = useCallback(async (force = false) => {
    if (!currentPageDataUrl || !pageInfo) { showToast('页面尚未渲染完成，请稍候', 'info'); return }
    // 验证 pageInfo 和 currentPageDataUrl 属于当前页
    if (pageInfo.pageNumber !== currentPage) {
      console.warn(`[PdfViewer] 检测页面不匹配: pageInfo.pageNumber=${pageInfo.pageNumber}, currentPage=${currentPage}`)
      showToast('页面状态异常，请稍候重试', 'warning')
      return
    }
    if (!force && pageDetections.has(currentPage)) { showToast(`第 ${currentPage} 页已检测`, 'info'); return }
    // First try cache-only lookup (quick scan may have populated bboxes).
    if (!force) {
      const cached = await loadCachedDetections(currentPage)
      if (cached) return
    }
    setIsDetecting(true)
    setSelectedDetection(null)
    try {
      const base64 = currentPageDataUrl.split(',')[1] || ''
      if (!base64) {
        throw new Error('无法获取页面图像数据')
      }
      const result = await detectPageMolecules({
        projectRoot,
        docId: doc.doc_id,
        page: currentPage,
        imageBase64: base64,
        pageWPts: pageInfo.originalWidth,
        pageHPts: pageInfo.originalHeight,
        imageW: Math.round(pageInfo.width),
        imageH: Math.round(pageInfo.height),
        force,
      })
      if (!result.success || !result.data) {
        throw new Error(result.error || '检测失败')
      }
      const results = result.data.results
      // 验证返回的结果确实属于当前页
      const validatedResults = results.filter(r => {
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
        if (r.page_idx !== null && r.page_idx !== undefined) {
          return r.page_idx === currentPage - 1
        }
        return true
      })
      if (validatedResults.length < results.length) {
        console.warn(`[PdfViewer] 过滤掉 ${results.length - validatedResults.length} 个不属于当前页的检测结果`)
      }
      const enriched = enrichResults(validatedResults, currentPage)
      setPageDetections(prev => { const next = new Map(prev); next.set(currentPage, enriched); return next })
      showToast(validatedResults.length > 0 ? `检测到 ${validatedResults.length} 个分子` : '未检测到分子',
        validatedResults.length > 0 ? 'success' : 'info')
    } catch (e) {
      console.error('Detection failed:', e)
      showToast('检测失败: ' + (e instanceof Error ? e.message : String(e)), 'error')
    } finally { setIsDetecting(false) }
  }, [currentPageDataUrl, pageInfo, currentPage, pageDetections, projectRoot, doc.doc_id, enrichResults, loadCachedDetections])

  const handleRecognizePage = useCallback(async () => {
    if (!currentPageDataUrl || !pageInfo) { showToast('页面尚未渲染完成，请稍候', 'info'); return }
    setIsDetecting(true)
    setSelectedDetection(null)
    try {
      const base64 = currentPageDataUrl.split(',')[1] || ''
      const result = await detectPageMolecules({
        projectRoot,
        docId: doc.doc_id,
        page: currentPage,
        imageBase64: base64,
        pageWPts: pageInfo.originalWidth,
        pageHPts: pageInfo.originalHeight,
        imageW: Math.round(pageInfo.width),
        imageH: Math.round(pageInfo.height),
        force: true,
      })
      if (!result.success || !result.data) {
        throw new Error(result.error || '识别失败')
      }
      const results = result.data.results
      const enriched = enrichResults(results, currentPage)
      setPageDetections(prev => { const next = new Map(prev); next.set(currentPage, enriched); return next })
      showToast(results.length > 0 ? `识别到 ${results.length} 个分子` : '未识别到分子',
        results.length > 0 ? 'success' : 'info')
    } catch (e) {
      console.error('Recognition failed:', e)
      showToast('识别失败: ' + (e instanceof Error ? e.message : String(e)), 'error')
    } finally { setIsDetecting(false) }
  }, [currentPageDataUrl, pageInfo, currentPage, projectRoot, doc.doc_id, enrichResults])

  const handleClearDetectionCache = useCallback(async () => {
    if (!projectRoot) return
    setIsDetecting(true)
    try {
      const result = await clearDocumentDetections(projectRoot, doc.doc_id)
      if (!result.success) {
        throw new Error(result.error || '清除缓存失败')
      }
      setPageDetections(new Map())
      setSelectedDetection(null)
      showToast('分子识别缓存已清除', 'success')
    } catch (e) {
      console.error('Failed to clear detection cache:', e)
      showToast('清除缓存失败: ' + (e instanceof Error ? e.message : String(e)), 'error')
    } finally { setIsDetecting(false) }
  }, [projectRoot, doc.doc_id])

  const handlePageRendered = useCallback((info: { pageNumber: number; width: number; height: number; originalWidth: number; originalHeight: number; scale: number }) => {
    // 只接受当前页的渲染结果，防止旧页面的数据污染
    if (info.pageNumber !== currentPage) {
      console.debug(`[PdfViewer] 忽略非当前页的渲染结果: page=${info.pageNumber}, current=${currentPage}`)
      return
    }
    // 验证页面尺寸合理性（防止异常数据）
    if (info.width <= 0 || info.height <= 0 || info.originalWidth <= 0 || info.originalHeight <= 0) {
      console.warn('[PdfViewer] 忽略异常的页面尺寸:', info)
      return
    }
    setPageInfo(info)
    pageInfoRef.current = info
  }, [currentPage])

  const handleImageReady = useCallback((pageNum: number, dataUrl: string) => {
    // 只接受当前页的图像数据
    if (pageNum !== currentPage) {
      console.debug(`[PdfViewer] 忽略非当前页的图像数据: page=${pageNum}, current=${currentPage}`)
      return
    }
    // 验证 dataUrl 有效性
    if (!dataUrl || !dataUrl.startsWith('data:image/')) {
      console.warn('[PdfViewer] 忽略无效的图像数据')
      return
    }
    setCurrentPageDataUrl(dataUrl)
  }, [currentPage])
  const handlePageCount = useCallback((count: number) => setPdfPageCount(count), [])

  // 切页时清空当前页渲染状态，避免旧页面的 dataUrl / pageInfo 被复用到新页，
  // 导致 MoldDet 把上一页的识别结果存到当前页（如第 2 页结果显示在第 3 页）。
  // 该 effect 必须声明在自动检测 effect 之前，以确保先清空再判断。
  useEffect(() => {
    setCurrentPageDataUrl(null)
    setPageInfo(null)
    pageInfoRef.current = null
    setSelectedDetection(null)
    // 清除非当前页的检测缓存，防止显示上一页的检测框
    setPageDetections(prev => {
      const next = new Map(prev)
      // 只保留当前页的检测结果，删除其他页的
      for (const key of next.keys()) {
        if (key !== currentPage) {
          next.delete(key)
        }
      }
      return next
    })
  }, [currentPage])

  // 进入分子检测模式后，当前页渲染完成自动触发检测
  useEffect(() => {
    if (!isDetectMode || !currentPageDataUrl || !pageInfo) return
    // 验证 pageInfo 确实属于当前页
    if (pageInfo.pageNumber !== currentPage) {
      console.debug(`[PdfViewer] 跳过自动检测: pageInfo.pageNumber=${pageInfo.pageNumber}, currentPage=${currentPage}`)
      return
    }
    if (pageDetections.has(currentPage) || isDetecting) return
    // 验证 currentPageDataUrl 有效性
    if (!currentPageDataUrl.startsWith('data:image/')) {
      console.debug('[PdfViewer] 跳过自动检测: 无效的 currentPageDataUrl')
      return
    }
    void handleDetectPage()
  }, [isDetectMode, currentPage, currentPageDataUrl, pageInfo, pageDetections, isDetecting, handleDetectPage])

  // Coref mode: 切页时清空非当前页的 coref 缓存 + 拉取当前页 labels/predictions
  useEffect(() => {
    if (!isCorefMode) return
    setCorefLabelsByPage(prev => {
      const next = new Map(prev)
      for (const k of next.keys()) if (k !== currentPage) next.delete(k)
      return next
    })
    setCorefPredictionsByPage(prev => {
      const next = new Map(prev)
      for (const k of next.keys()) if (k !== currentPage) next.delete(k)
      return next
    })
  }, [isCorefMode, currentPage])

  const loadCorefForPage = useCallback(async (pageNum: number) => {
    if (!projectRoot || !doc.doc_id) return
    if (corefLabelsByPage.has(pageNum) && corefPredictionsByPage.has(pageNum)) return
    setIsLoadingCoref(true)
    try {
      const [labels, preds] = await Promise.all([
        getFigureLabels(projectRoot, doc.doc_id, pageNum),
        getCorefPredictions(projectRoot, doc.doc_id, pageNum),
      ])
      setCorefLabelsByPage(prev => { const next = new Map(prev); next.set(pageNum, labels); return next })
      setCorefPredictionsByPage(prev => { const next = new Map(prev); next.set(pageNum, preds); return next })
    } catch (e) {
      console.warn('Failed to load coref annotations:', e)
      showToast('Coref 数据加载失败', 'error')
    } finally {
      setIsLoadingCoref(false)
    }
  }, [projectRoot, doc.doc_id, corefLabelsByPage, corefPredictionsByPage])

  // 进入 coref 模式或切页时拉取数据
  useEffect(() => {
    if (!isCorefMode) return
    void loadCorefForPage(currentPage)
  }, [isCorefMode, currentPage, loadCorefForPage])

  const refreshCorefForPage = useCallback(async () => {
    setCorefLabelsByPage(prev => { const next = new Map(prev); next.delete(currentPage); return next })
    setCorefPredictionsByPage(prev => { const next = new Map(prev); next.delete(currentPage); return next })
    await loadCorefForPage(currentPage)
  }, [currentPage, loadCorefForPage])

  const handleSaveMolecule = useCallback((newSmiles: string) => {
    if (selectedDetection === null) return
    setPageDetections(prev => {
      const next = new Map(prev)
      const detections = next.get(currentPage) || []
      const updated = [...detections]
      updated[selectedDetection] = { ...updated[selectedDetection], esmiles: newSmiles }
      next.set(currentPage, updated)
      return next
    })
    showToast('分子已更新', 'success')
  }, [selectedDetection, currentPage])

  const handleTextContent = useCallback((_page: number, items: { str: string; x: number; y: number; width: number; height: number }[]) => {
    setPageTextItems(prev => { const next = new Map(prev); next.set(_page, items); return next })
    const totalChars = items.reduce((s, i) => s + i.str.length, 0)
    if (totalChars > 10) {
      setPdfOcrSummary(prev => {
        const newTotal = (prev?.totalChars ?? 0) + totalChars
        return {
          totalChars: newTotal,
          textDensity: newTotal > 500 ? 'rich' : newTotal > 100 ? 'medium' : 'sparse',
        }
      })
    }
  }, [])

  const handleZoomIn = useCallback(() => setPdfScale(s => Math.min(s + 0.3, 5)), [])
  const handleZoomOut = useCallback(() => setPdfScale(s => Math.max(s - 0.3, 0.5)), [])
  const handleZoomReset = useCallback(() => setPdfScale(1.5), [])

  const handleLoadImages = useCallback(async () => {
    if (extractedImages.length > 0) { setShowImagePanel(true); return }
    setIsLoadingImages(true)
    try {
      const result = await extractPdfImages(absDocPath, 512, 128, 'pdf_inspector')
      if (!result.success) {
        throw new Error(result.error || '图片提取失败')
      }
      setExtractedImages(result.data || [])
      setShowImagePanel(true)
    } catch (e) {
      console.error('Failed to load images:', e)
      showToast('图片提取失败', 'error')
    } finally { setIsLoadingImages(false) }
  }, [absDocPath, extractedImages.length])

  const handleLoadOcr = useCallback(async () => {
    if (ocrBlocks.length > 0) { setShowOcrPanel(true); return }
    setIsLoadingOcr(true)
    try {
      const result = await getDocumentOcrLayout(absDocPath, doc.doc_id)
      setOcrBlocks(result.blocks)
      setShowOcrPanel(true)
      const hasBlocks = result.blocks.length > 0
      showToast(
        hasBlocks ? `加载 ${result.blocks.length} 个 OCR 块` : getOcrEmptyHint(result.parser),
        hasBlocks ? 'success' : 'info',
      )
    } catch (e) {
      console.error('Failed to load OCR layout:', e)
      const msg = e instanceof Error ? e.message : String(e)
      showToast(`OCR 布局加载失败：${msg}`, 'error')
    } finally { setIsLoadingOcr(false) }
  }, [absDocPath, doc.doc_id, ocrBlocks.length])

  const [imageBlobUrls, setImageBlobUrls] = useState<Map<string, string>>(new Map())
  useEffect(() => {
    if (!projectRoot || extractedImages.length === 0) { setImageBlobUrls(new Map()); return }
    const cleanRoot = projectRoot.replace(/^\\\\\?\\/, '').replace(/^\?\//, '').replace(/\\/g, '/').replace(/\/$/, '')
    const newMap = new Map<string, string>()
    for (const img of extractedImages) {
      if (!img.rel_path) continue
      newMap.set(img.rel_path, convertFileSrc(`${cleanRoot}/${img.rel_path.replace(/\\/g, '/')}`, 'mbforge'))
    }
    setImageBlobUrls(newMap)
  }, [extractedImages, projectRoot])

  const handleJumpToPage = useCallback(() => {
    const n = parseInt(pageJumpInput, 10)
    if (n > 0) { setCurrentPage(n); setSelectedDetection(null); setPageJumpInput('') }
  }, [pageJumpInput])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp' || e.key === 'PageUp') {
      e.preventDefault()
      setCurrentPage(p => Math.max(1, p - 1))
      setSelectedDetection(null)
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === 'PageDown' || e.key === ' ') {
      e.preventDefault()
      setCurrentPage(p => Math.min(pdfPageCount || 1, p + 1))
      setSelectedDetection(null)
    }
  }, [pdfPageCount])

  const handleWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    const el = pdfScrollRef.current
    if (!el || pdfLoading || !pdfUrl) return
    const { scrollTop, scrollHeight, clientHeight } = el
    const atTop = scrollTop <= 0
    const atBottom = scrollTop + clientHeight >= scrollHeight - 1
    if ((e.deltaY < 0 && atTop) || (e.deltaY > 0 && atBottom)) {
      // 不再调用 preventDefault()，避免 passive event listener 警告；
      // 用时间门控降低连续滚轮触发翻页的速度。
      const now = Date.now()
      if (now - wheelSwitchAtRef.current < WHEEL_SWITCH_COOLDOWN_MS) return
      wheelSwitchAtRef.current = now
      if (e.deltaY < 0) {
        setCurrentPage(p => Math.max(1, p - 1))
      } else {
        setCurrentPage(p => Math.min(pdfPageCount || 1, p + 1))
      }
      setSelectedDetection(null)
    }
  }, [pdfLoading, pdfUrl, pdfPageCount])

  useEffect(() => { pdfScrollRef.current?.focus() }, [doc.doc_id])

  // 滚动到指定检测结果的位置（支持单页和连续模式）
  const scrollToDetection = useCallback((detection: ExtractionResult) => {
    if (!detection.bbox_pdf || !pageInfoRef.current) return
    const container = pdfScrollRef.current
    if (!container) return

    const [, y1, , y2] = detection.bbox_pdf
    const info = pageInfoRef.current

    // 检查是否是连续模式（容器内有 [data-page] 元素）
    const isContinuousMode = container.querySelector('[data-page]')

    if (isContinuousMode) {
      // 连续模式：找到当前页的元素，计算偏移量
      const pageEl = container.querySelector(`[data-page="${detection.page_idx !== null ? detection.page_idx + 1 : currentPage}"]`)
      if (pageEl) {
        const pageRect = pageEl.getBoundingClientRect()
        const containerRect = container.getBoundingClientRect()
        // 计算检测框在页面内的相对位置
        const cssY = (info.originalHeight - y2) * info.scale
        const cssY2 = (info.originalHeight - y1) * info.scale
        const centerY = (cssY + cssY2) / 2
        // 滚动到检测框居中
        container.scrollTo({
          top: pageEl.scrollTop + (pageRect.top - containerRect.top) + centerY - container.clientHeight / 2,
          behavior: 'smooth',
        })
      }
    } else {
      // 单页模式：直接计算 CSS 坐标
      const cssY = (info.originalHeight - y2) * info.scale
      const cssY2 = (info.originalHeight - y1) * info.scale
      const centerY = (cssY + cssY2) / 2
      container.scrollTo({
        top: Math.max(0, centerY - container.clientHeight / 2),
        behavior: 'smooth',
      })
    }
  }, [currentPage])

  return {
    pdfViewMode, setPdfViewMode, isDetectMode, isOcrMode, isCorefMode,
    isSinglePageMode,
    confidenceThreshold, setConfidenceThreshold,
    currentPage, setCurrentPage, pageDetections, setPageDetections,
    isDetecting, selectedDetection, setSelectedDetection,
    pageInfo, pageInfoRef, currentPageDataUrl, pdfScale,
    showTextLayer, setShowTextLayer, pageTextItems,
    pdfOcrSummary, pageJumpInput, setPageJumpInput,
    showTextPanel, setShowTextPanel, pdfPageCount,
    showImagePanel, setShowImagePanel, extractedImages,
    isLoadingImages, ocrBlocks, setOcrBlocks,
    showOcrPanel, setShowOcrPanel, selectedOcrIndex, setSelectedOcrIndex,
    hoveredOcrIndex, setHoveredOcrIndex, isLoadingOcr,
    corefThreshold, setCorefThreshold,
    corefLabels: corefLabelsByPage.get(currentPage) ?? [],
    corefPredictions: corefPredictionsByPage.get(currentPage) ?? [],
    isLoadingCoref,
    refreshCorefForPage,
    pdfUrl, pdfLoading, pdfScrollRef,
    currentDetections, currentTextItems, currentTextTotal, hasTextLayer, canDetect,
    imageBlobUrls,
    handleDetectPage, handleRecognizePage, handleClearDetectionCache, handlePageRendered, handleImageReady, handlePageCount,
    handleSaveMolecule, handleTextContent,
    handleZoomIn, handleZoomOut, handleZoomReset,
    handleLoadImages, handleLoadOcr, handleJumpToPage,
    handleKeyDown, handleWheel, scrollToDetection,
  }
}
