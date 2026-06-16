import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { convertFileSrc } from '@tauri-apps/api/core'
import { cachedExtractPage, getCachedPageDetections, clearDetectionCacheForDoc } from '../../../api/tauri/detection_cache'
import { parsePdf, getDocumentOcrLayout } from '../../../api/tauri/pdf'
import { showToast } from '../../../hooks/useToast'
import { extractRoiText } from '../../../utils/roiText'
import type { DocumentEntry, ExtractionResult } from '../../../types'
import type { ImageRef, OcrBlock } from '../../../api/tauri/pdf'

export function usePdfViewer(doc: DocumentEntry, projectRoot: string, initialMode?: 'read' | 'detect' | 'ocr') {
  const [pdfViewMode, setPdfViewMode] = useState(initialMode ?? 'read')
  const isDetectMode = pdfViewMode === 'detect'
  const isOcrMode = pdfViewMode === 'ocr'
  const [scrollMode, setScrollMode] = useState<'single' | 'continuous'>('continuous')
  const isSinglePageMode = isDetectMode || isOcrMode || scrollMode === 'single'

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

  const [pdfUrl, setPdfUrl] = useState('')
  const [pdfLoading, setPdfLoading] = useState(true)
  const pdfScrollRef = useRef<HTMLDivElement>(null)
  const autoLoadOcrDone = useRef(false)
  const wheelSwitchAtRef = useRef(0)
  const WHEEL_SWITCH_COOLDOWN_MS = 400

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

  useEffect(() => {
    if (isDetectMode || isOcrMode) setScrollMode('single')
  }, [isDetectMode, isOcrMode])

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
    if (!absDocPath) { setPdfLoading(false); return }
    const url = convertFileSrc(absDocPath, 'mbforge')
    if (!cancelled) { setPdfUrl(url); setPdfLoading(false) }
    return () => { cancelled = true }
  }, [absDocPath])

  useEffect(() => {
    if (initialMode === 'ocr' && !autoLoadOcrDone.current) {
      autoLoadOcrDone.current = true
      setIsLoadingOcr(true)
      getDocumentOcrLayout(absDocPath, doc.doc_id)
        .then(result => {
          setOcrBlocks(result.blocks || [])
          setShowOcrPanel(true)
          const hasBlocks = result.blocks.length > 0
          showToast(
            hasBlocks ? `加载 ${result.blocks.length} 个 OCR 块` : getOcrEmptyHint(result.parser),
            hasBlocks ? 'success' : 'info',
          )
        })
        .catch(e => {
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
      const resp = await getCachedPageDetections({ projectRoot, docId: doc.doc_id, page: pageNum })
      if (resp.count > 0 && resp.results.length > 0) {
        const results = resp.results as ExtractionResult[]
        const enriched = enrichResults(results, pageNum)
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
      const resp = await cachedExtractPage({
        projectRoot, docId: doc.doc_id, page: currentPage, imageBase64: base64,
        pageWPts: pageInfo.originalWidth, pageHPts: pageInfo.originalHeight,
        imageW: Math.round(pageInfo.width), imageH: Math.round(pageInfo.height),
        force,
      })
      if (resp.source === 'sidecar_error') throw new Error(resp.error || 'sidecar error')
      const results = resp.results as ExtractionResult[]
      const enriched = enrichResults(results, currentPage)
      setPageDetections(prev => { const next = new Map(prev); next.set(currentPage, enriched); return next })
      showToast(results.length > 0 ? `检测到 ${results.length} 个分子` : '未检测到分子',
        results.length > 0 ? 'success' : 'info')
    } catch (e) {
      console.error('Detection failed:', e)
      showToast('检测失败: ' + (e instanceof Error ? e.message : String(e)), 'error')
    } finally { setIsDetecting(false) }
  }, [currentPageDataUrl, pageInfo, currentPage, pageDetections, projectRoot, doc.doc_id, enrichResults])

  const handleRecognizePage = useCallback(async () => {
    if (!currentPageDataUrl || !pageInfo) { showToast('页面尚未渲染完成，请稍候', 'info'); return }
    setIsDetecting(true)
    setSelectedDetection(null)
    try {
      const base64 = currentPageDataUrl.split(',')[1] || ''
      const resp = await cachedExtractPage({
        projectRoot, docId: doc.doc_id, page: currentPage, imageBase64: base64,
        pageWPts: pageInfo.originalWidth, pageHPts: pageInfo.originalHeight,
        imageW: Math.round(pageInfo.width), imageH: Math.round(pageInfo.height),
        force: true,
      })
      if (resp.source === 'sidecar_error') throw new Error(resp.error || 'sidecar error')
      const results = resp.results as ExtractionResult[]
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
      await clearDetectionCacheForDoc(projectRoot, doc.doc_id)
      setPageDetections(new Map())
      setSelectedDetection(null)
      showToast('分子识别缓存已清除', 'success')
    } catch (e) {
      console.error('Failed to clear detection cache:', e)
      showToast('清除缓存失败: ' + (e instanceof Error ? e.message : String(e)), 'error')
    } finally { setIsDetecting(false) }
  }, [projectRoot, doc.doc_id])

  const handlePageRendered = useCallback((info: { pageNumber: number; width: number; height: number; originalWidth: number; originalHeight: number; scale: number }) => {
    if (info.pageNumber !== currentPage) return
    setPageInfo(info)
    pageInfoRef.current = info
  }, [currentPage])

  const handleImageReady = useCallback((pageNum: number, dataUrl: string) => {
    if (pageNum !== currentPage) return
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
  }, [currentPage])

  // 进入分子检测模式后，当前页渲染完成自动触发检测
  useEffect(() => {
    if (!isDetectMode || !currentPageDataUrl || !pageInfo) return
    if (pageDetections.has(currentPage) || isDetecting) return
    handleDetectPage()
  }, [isDetectMode, currentPage, currentPageDataUrl, pageInfo, pageDetections, isDetecting, handleDetectPage])

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
      setPdfOcrSummary(prev => ({
        totalChars: (prev?.totalChars ?? 0) + totalChars,
        textDensity: totalChars > 500 ? 'rich' : totalChars > 100 ? 'medium' : 'sparse',
      }))
    }
  }, [])

  const handleZoomIn = useCallback(() => setPdfScale(s => Math.min(s + 0.3, 5)), [])
  const handleZoomOut = useCallback(() => setPdfScale(s => Math.max(s - 0.3, 0.5)), [])
  const handleZoomReset = useCallback(() => setPdfScale(1.5), [])

  const handleLoadImages = useCallback(async () => {
    if (extractedImages.length > 0) { setShowImagePanel(true); return }
    setIsLoadingImages(true)
    try {
      const result = await parsePdf(absDocPath, 512, 128, 'pdf_inspector')
      setExtractedImages(result.images || [])
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
      setOcrBlocks(result.blocks || [])
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

  return {
    pdfViewMode, setPdfViewMode, isDetectMode, isOcrMode,
    scrollMode, setScrollMode, isSinglePageMode,
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
    pdfUrl, pdfLoading, pdfScrollRef,
    currentDetections, currentTextItems, currentTextTotal, hasTextLayer, canDetect,
    imageBlobUrls,
    handleDetectPage, handleRecognizePage, handleClearDetectionCache, handlePageRendered, handleImageReady, handlePageCount,
    handleSaveMolecule, handleTextContent,
    handleZoomIn, handleZoomOut, handleZoomReset,
    handleLoadImages, handleLoadOcr, handleJumpToPage,
    handleKeyDown, handleWheel,
  }
}
