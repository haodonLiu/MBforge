import { useState, useRef, useEffect, useCallback } from 'react'
import { convertFileSrc } from '@tauri-apps/api/core'
import { cachedExtractPage, getCachedPageDetections } from '../../../api/tauri/detection_cache'
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
    width: number; height: number; originalWidth: number; originalHeight: number; scale: number
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

  const currentDetections = pageDetections.get(currentPage) || []
  const currentTextItems = pageTextItems.get(currentPage) || []
  const currentTextTotal = currentTextItems.reduce((s, i) => s + i.str.length, 0)
  const hasTextLayer = currentTextTotal > 10
  const canDetect = !!currentPageDataUrl && !!pageInfo && !pageDetections.has(currentPage)

  useEffect(() => {
    if (isDetectMode || isOcrMode) setScrollMode('single')
  }, [isDetectMode, isOcrMode])

  useEffect(() => {
    let cancelled = false
    setPdfUrl('')
    setPdfLoading(true)
    const root = projectRoot
    if (!root) { setPdfLoading(false); return }
    const normalizePath = (p: string) => p.replace(/^\\\\\?\\/, '').replace(/^\?\//, '').replace(/\\/g, '/')
    const pdfPath = doc.source_path || doc.path
    const absPath = pdfPath.includes(':') || pdfPath.startsWith('/')
      ? normalizePath(pdfPath)
      : `${normalizePath(root).replace(/\/$/, '')}/${pdfPath.replace(/\\/g, '/')}`
    const url = convertFileSrc(absPath, 'mbforge')
    if (!cancelled) { setPdfUrl(url); setPdfLoading(false) }
    return () => { cancelled = true }
  }, [doc.path, doc.source_path, projectRoot])

  useEffect(() => {
    if (initialMode === 'ocr' && !autoLoadOcrDone.current) {
      autoLoadOcrDone.current = true
      setIsLoadingOcr(true)
      getDocumentOcrLayout(doc.path, doc.doc_id)
        .then(result => {
          setOcrBlocks(result.blocks || [])
          setShowOcrPanel(true)
          showToast(result.blocks.length > 0 ? `加载 ${result.blocks.length} 个 OCR 块` : '未找到 OCR 布局数据',
            result.blocks.length > 0 ? 'success' : 'info')
        })
        .catch(e => { console.error('Failed to load OCR layout:', e); showToast('OCR 布局加载失败', 'error') })
        .finally(() => setIsLoadingOcr(false))
    }
  }, [doc.path, doc.doc_id, initialMode])

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

  const handleDetectPage = useCallback(async () => {
    if (!currentPageDataUrl || !pageInfo) { showToast('页面尚未渲染完成，请稍候', 'info'); return }
    if (pageDetections.has(currentPage)) { showToast(`第 ${currentPage} 页已检测`, 'info'); return }
    // First try cache-only lookup (quick scan may have populated bboxes).
    const cached = await loadCachedDetections(currentPage)
    if (cached) return
    setIsDetecting(true)
    setSelectedDetection(null)
    try {
      const base64 = currentPageDataUrl.split(',')[1] || ''
      const resp = await cachedExtractPage({
        projectRoot, docId: doc.doc_id, page: currentPage, imageBase64: base64,
        pageWPts: pageInfo.originalWidth, pageHPts: pageInfo.originalHeight,
        imageW: Math.round(pageInfo.width), imageH: Math.round(pageInfo.height),
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

  const handlePageRendered = useCallback((info: { pageNumber: number; width: number; height: number; originalWidth: number; originalHeight: number; scale: number }) => {
    setPageInfo(info); pageInfoRef.current = info
  }, [])

  // 进入分子检测模式后，当前页渲染完成自动触发检测
  useEffect(() => {
    if (!isDetectMode || !currentPageDataUrl || !pageInfo) return
    if (pageDetections.has(currentPage) || isDetecting) return
    handleDetectPage()
  }, [isDetectMode, currentPage, currentPageDataUrl, pageInfo, pageDetections, isDetecting, handleDetectPage])

  const handleImageReady = useCallback((_num: number, dataUrl: string) => setCurrentPageDataUrl(dataUrl), [])
  const handlePageCount = useCallback((count: number) => setPdfPageCount(count), [])

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
      const result = await parsePdf(doc.path, 512, 128, 'pdf_inspector')
      setExtractedImages(result.images || [])
      setShowImagePanel(true)
    } catch (e) {
      console.error('Failed to load images:', e)
      showToast('图片提取失败', 'error')
    } finally { setIsLoadingImages(false) }
  }, [doc.path, extractedImages.length])

  const handleLoadOcr = useCallback(async () => {
    if (ocrBlocks.length > 0) { setShowOcrPanel(true); return }
    setIsLoadingOcr(true)
    try {
      const result = await getDocumentOcrLayout(doc.path, doc.doc_id)
      setOcrBlocks(result.blocks || [])
      setShowOcrPanel(true)
      showToast(result.blocks.length > 0 ? `加载 ${result.blocks.length} 个 OCR 块` : '未找到 OCR 布局数据',
        result.blocks.length > 0 ? 'success' : 'info')
    } catch (e) {
      console.error('Failed to load OCR layout:', e)
      showToast('OCR 布局加载失败', 'error')
    } finally { setIsLoadingOcr(false) }
  }, [doc.path, doc.doc_id, ocrBlocks.length])

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
    if (e.deltaY < 0 && atTop) {
      e.preventDefault(); setCurrentPage(p => Math.max(1, p - 1)); setSelectedDetection(null)
    } else if (e.deltaY > 0 && atBottom) {
      e.preventDefault(); setCurrentPage(p => Math.min(pdfPageCount || 1, p + 1)); setSelectedDetection(null)
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
    handleDetectPage, handleRecognizePage, handlePageRendered, handleImageReady, handlePageCount,
    handleSaveMolecule, handleTextContent,
    handleZoomIn, handleZoomOut, handleZoomReset,
    handleLoadImages, handleLoadOcr, handleJumpToPage,
    handleKeyDown, handleWheel,
  }
}
