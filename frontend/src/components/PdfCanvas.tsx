import { useEffect, useRef, useState, useCallback } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import * as pdfjsLib from 'pdfjs-dist'

function isTextItem(v: unknown): v is { str: string; transform: number[]; width: number; height: number } {
  return typeof v === 'object' && v !== null && 'str' in v && typeof v.str === 'string'
}

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.mjs',
  import.meta.url,
).toString()

const DOC_CACHE_MAX = 3
const docCache = new Map<string, Promise<PDFDocumentProxy>>()

function getCachedDoc(url: string): Promise<PDFDocumentProxy> {
  let promise = docCache.get(url)
  if (!promise) {
    promise = pdfjsLib.getDocument(url).promise
    docCache.set(url, promise)
    if (docCache.size > DOC_CACHE_MAX) {
      const oldest = docCache.keys().next().value
      if (oldest) docCache.delete(oldest)
    }
  } else {
    docCache.delete(url)
    docCache.set(url, promise)
  }
  return promise
}

interface PageInfo {
  pageNumber: number
  width: number
  height: number
  originalWidth: number
  originalHeight: number
  scale: number
}

interface Props {
  url: string
  pageNumber: number
  scale?: number
  generateImage?: boolean
  showTextLayer?: boolean
  onPageRendered?: (info: PageInfo) => void
  onImageReady?: (pageNumber: number, dataUrl: string) => void
  onTextContent?: (pageNumber: number, items: { str: string; x: number; y: number; width: number; height: number }[]) => void
  onTextLayerClick?: (pageNumber: number) => void
  onPageCount?: (count: number) => void
  className?: string
  style?: React.CSSProperties
}

export default function PdfCanvas({
  url,
  pageNumber,
  scale = 1.5,
  generateImage = false,
  showTextLayer = true,
  onPageRendered,
  onImageReady,
  onTextContent,
  onTextLayerClick,
  onPageCount,
  className,
  style,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const textLayerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const totalPagesRef = useRef(0)
  const [totalPages, setTotalPages] = useState(0)
  const pdfDocRef = useRef<PDFDocumentProxy | null>(null)
  const renderTaskRef = useRef<pdfjsLib.RenderTask | null>(null)

  const onPageRenderedRef = useRef(onPageRendered)
  const onImageReadyRef = useRef(onImageReady)
  const onTextContentRef = useRef(onTextContent)
  const onPageCountRef = useRef(onPageCount)
  const generateImageRef = useRef(generateImage)
  onPageRenderedRef.current = onPageRendered
  onImageReadyRef.current = onImageReady
  onTextContentRef.current = onTextContent
  onPageCountRef.current = onPageCount
  generateImageRef.current = generateImage

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    getCachedDoc(url)
      .then(doc => {
        if (cancelled) return
        pdfDocRef.current = doc
        totalPagesRef.current = doc.numPages
        setTotalPages(doc.numPages)
        onPageCountRef.current?.(doc.numPages)
      })
      .catch(e => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load PDF')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [url])

  const renderTextLayerImpl = useCallback(async (page: pdfjsLib.PDFPageProxy) => {
    const container = textLayerRef.current
    if (!container) return

    const logicalViewport = page.getViewport({ scale })
    const textContent = await page.getTextContent()

    container.innerHTML = ''
    container.style.width = `${logicalViewport.width}px`
    container.style.height = `${logicalViewport.height}px`

    if (onTextContentRef.current) {
      const items = (textContent.items as unknown[])
        .filter(isTextItem)
        .map(item => ({
          str: item.str,
          x: item.transform[4],
          y: item.transform[5],
          width: item.width,
          height: item.height,
        }))
      onTextContentRef.current(pageNumber, items)
    }
  }, [pageNumber, scale])

  const renderPage = useCallback(async () => {
    const doc = pdfDocRef.current
    const canvas = canvasRef.current
    const textLayerEl = textLayerRef.current
    if (!doc || !canvas) return

    // 取消上一次未完成的渲染 — pdf.js 不允许同一 canvas 并发 render()
    if (renderTaskRef.current) {
      try { renderTaskRef.current.cancel() } catch { /* ignore */ }
      renderTaskRef.current = null
    }

    try {
      const page = await doc.getPage(pageNumber)
      const dpr = window.devicePixelRatio || 1
      const viewport = page.getViewport({ scale: scale * dpr })
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      canvas.width = viewport.width
      canvas.height = viewport.height
      canvas.style.width = `${viewport.width / dpr}px`
      canvas.style.height = `${viewport.height / dpr}px`
      ctx.clearRect(0, 0, viewport.width, viewport.height)
      ctx.scale(dpr, dpr)
      const task = page.render({
        canvasContext: ctx,
        viewport: page.getViewport({ scale }),
      })
      renderTaskRef.current = task
      try {
        await task.promise
      } catch (e) {
        // 取消会抛 RenderCancelledException — 静默吞掉
        if ((e as Error)?.message?.includes('cancelled')) return
        throw e
      } finally {
        if (renderTaskRef.current === task) renderTaskRef.current = null
      }

      const originalViewport = page.getViewport({ scale: 1 })
      onPageRenderedRef.current?.({
        pageNumber,
        width: viewport.width / dpr,
        height: viewport.height / dpr,
        originalWidth: originalViewport.width,
        originalHeight: originalViewport.height,
        scale: scale,
      })

      if (generateImageRef.current) {
        ctx.setTransform(1, 0, 0, 1, 0, 0)
        onImageReadyRef.current?.(pageNumber, canvas.toDataURL('image/png'))
      }

      if (textLayerEl) {
        renderTextLayerImpl(page)
      }
    } catch (e) {
      console.error('PDF render error:', e)
    }
  }, [pageNumber, scale, renderTextLayerImpl])

  useEffect(() => {
    if (!loading && !error) renderPage()
  }, [loading, error, renderPage])

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ position: 'relative', ...style }}
    >
      {loading && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          height: '100%', color: 'var(--text-muted)', fontSize: '13px',
        }}>
          加载 PDF...
        </div>
      )}
      {error && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          height: '100%', color: 'var(--danger)', fontSize: '13px',
        }}>
          {error}
        </div>
      )}
      <canvas
        ref={canvasRef}
        style={{
          display: loading || error ? 'none' : 'block',
          maxWidth: '100%',
          margin: '0 auto',
        }}
      />
      <div
        ref={textLayerRef}
        onClick={() => onTextLayerClick?.(pageNumber)}
        style={{
          position: 'absolute',
          top: 0,
          left: '50%',
          transform: 'translateX(-50%)',
          cursor: showTextLayer ? 'text' : 'default',
          pointerEvents: showTextLayer ? 'auto' : 'none',
          display: loading || error || !showTextLayer ? 'none' : 'block',
          zIndex: 1,
          background: 'transparent',
        }}
        title="点击打开当前页识别文本"
      />
      {totalPages > 0 && (
        <div style={{
          position: 'absolute', bottom: '8px', left: '50%',
          transform: 'translateX(-50%)',
          fontSize: '11px', color: 'var(--text-muted)',
          background: 'var(--bg-surface)', padding: '2px 8px',
          borderRadius: '4px', border: '1px solid var(--border)',
          zIndex: 2,
        }}>
          {pageNumber} / {totalPages}
        </div>
      )}
    </div>
  )
}
