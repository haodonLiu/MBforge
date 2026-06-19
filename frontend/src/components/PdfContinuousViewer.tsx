import { useEffect, useRef, useState, useCallback, forwardRef, useImperativeHandle } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import * as pdfjsLib from 'pdfjs-dist'

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

interface ScrollProgress {
  scrollTop: number
  scrollHeight: number
  clientHeight: number
  progress: number
}

interface Props {
  url: string
  scale?: number
  onPageChange?: (page: number) => void
  onPageCount?: (count: number) => void
  onScrollProgress?: (progress: ScrollProgress) => void
}

interface PageData {
  pageNumber: number
  width: number
  height: number
}

const PdfContinuousViewer = forwardRef<HTMLDivElement, Props>(
  function PdfContinuousViewer({ url, scale = 1.5, onPageChange, onPageCount, onScrollProgress }, ref) {
    const containerRef = useRef<HTMLDivElement>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [pageCount, setPageCount] = useState(0)
    const [pages, setPages] = useState<PageData[]>([])
    const [visiblePages, setVisiblePages] = useState<Set<number>>(new Set())
    const pdfDocRef = useRef<PDFDocumentProxy | null>(null)
    const canvasRefs = useRef<Map<number, HTMLCanvasElement>>(new Map())
    const renderedPages = useRef<Set<number>>(new Set())
    const renderTasksRef = useRef<Map<number, any>>(new Map())
    const onPageChangeRef = useRef(onPageChange)
    const onPageCountRef = useRef(onPageCount)
    const onScrollProgressRef = useRef(onScrollProgress)
    onPageChangeRef.current = onPageChange
    onPageCountRef.current = onPageCount
    onScrollProgressRef.current = onScrollProgress

    // 暴露内部容器给外部 ref
    useImperativeHandle(ref, () => containerRef.current!, [])

    // Load document
    useEffect(() => {
      let cancelled = false
      setLoading(true)
      setError(null)
      setPages([])
      setVisiblePages(new Set())
      renderedPages.current.clear()
      canvasRefs.current.clear()

      getCachedDoc(url)
        .then(async (doc) => {
          if (cancelled) return
          pdfDocRef.current = doc
          const count = doc.numPages
          setPageCount(count)
          onPageCountRef.current?.(count)

          const pageData: PageData[] = []
          for (let i = 1; i <= count; i++) {
            const page = await doc.getPage(i)
            const vp = page.getViewport({ scale })
            pageData.push({ pageNumber: i, width: vp.width, height: vp.height })
          }
          if (!cancelled) setPages(pageData)
        })
        .catch((e) => {
          if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load PDF')
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })

      return () => {
        cancelled = true
        renderTasksRef.current.forEach((task) => {
          try { task.cancel() } catch { /* ignore */ }
        })
        renderTasksRef.current.clear()
        renderedPages.current.clear()
        canvasRefs.current.clear()
      }
    }, [url, scale])

    const cancelInFlight = useCallback((pageNum: number) => {
      const task = renderTasksRef.current.get(pageNum)
      if (task) {
        try { task.cancel() } catch { /* ignore */ }
        renderTasksRef.current.delete(pageNum)
      }
    }, [])

    const renderPageToCanvas = useCallback(async (pageNum: number, canvas: HTMLCanvasElement) => {
      const doc = pdfDocRef.current
      if (!doc || renderedPages.current.has(pageNum)) return
      cancelInFlight(pageNum)
      renderedPages.current.add(pageNum)
      try {
        const page = await doc.getPage(pageNum)
        const dpr = window.devicePixelRatio || 1
        const viewport = page.getViewport({ scale: scale * dpr })
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          renderedPages.current.delete(pageNum)
          return
        }

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
        renderTasksRef.current.set(pageNum, task)
        await task.promise
        renderTasksRef.current.delete(pageNum)
      } catch (e: unknown) {
        const name = (e as { name?: string } | null)?.name
        if (name !== 'RenderingCancelledException') {
          console.error(`Render page ${pageNum} failed:`, e)
          renderedPages.current.delete(pageNum)
        }
        renderTasksRef.current.delete(pageNum)
      }
    }, [scale, cancelInFlight])

    // Render visible pages
    useEffect(() => {
      visiblePages.forEach((pageNum) => {
        const canvas = canvasRefs.current.get(pageNum)
        if (!canvas) return
        renderPageToCanvas(pageNum, canvas)
      })
    }, [visiblePages, renderPageToCanvas])

    // IntersectionObserver to track visible pages
    useEffect(() => {
      const container = containerRef.current
      if (!container || pages.length === 0) return

      let timer: ReturnType<typeof setTimeout>
      const observer = new IntersectionObserver(
        (entries) => {
          clearTimeout(timer)
          timer = setTimeout(() => {
            const newVisible = new Set<number>()
            entries.forEach((entry) => {
              const pageNum = Number((entry.target as HTMLElement).dataset.page)
              if (entry.isIntersecting) {
                newVisible.add(pageNum)
              }
            })
            setVisiblePages(newVisible)

            const sorted = Array.from(newVisible).sort((a, b) => a - b)
            if (sorted.length > 0) {
              onPageChangeRef.current?.(sorted[0])
            }
          }, 120)
        },
        { root: container, threshold: 0.1 }
      )

      const pageEls = container.querySelectorAll('[data-page]')
      pageEls.forEach((el) => observer.observe(el))

      return () => { observer.disconnect(); clearTimeout(timer) }
    }, [pages])

    // 滚动进度回调（节流 50ms）
    const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    const handleScroll = useCallback(() => {
      if (scrollTimerRef.current) return
      scrollTimerRef.current = setTimeout(() => {
        scrollTimerRef.current = null
        if (!containerRef.current) return
        const { scrollTop, scrollHeight, clientHeight } = containerRef.current
        onScrollProgressRef.current?.({
          scrollTop,
          scrollHeight,
          clientHeight,
          progress: scrollHeight > clientHeight
            ? scrollTop / (scrollHeight - clientHeight)
            : 0,
        })
      }, 50)
    }, [])

    const visiblePagesRef = useRef(visiblePages)
    const renderPageToCanvasRef = useRef(renderPageToCanvas)
    visiblePagesRef.current = visiblePages
    renderPageToCanvasRef.current = renderPageToCanvas

    const setCanvasRef = useCallback((pageNum: number, el: HTMLCanvasElement | null) => {
      const oldEl = canvasRefs.current.get(pageNum)
      if (el === oldEl) return
      if (el) {
        canvasRefs.current.set(pageNum, el)
        cancelInFlight(pageNum)
        renderedPages.current.delete(pageNum)
        if (visiblePagesRef.current.has(pageNum)) {
          renderPageToCanvasRef.current(pageNum, el)
        }
      } else {
        canvasRefs.current.delete(pageNum)
        cancelInFlight(pageNum)
        renderedPages.current.delete(pageNum)
      }
    }, [cancelInFlight])

    if (loading) {
      return (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          height: '60vh', color: 'var(--text-muted)', fontSize: '13px',
        }}>
          加载 PDF...
        </div>
      )
    }

    if (error) {
      return (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          height: '60vh', color: 'var(--danger)', fontSize: '13px',
        }}>
          {error}
        </div>
      )
    }

    return (
      <div
        ref={containerRef}
        onScroll={handleScroll}
        style={{
          width: '100%', height: '100%',
          overflowY: 'auto',
        }}
      >
        <div style={{
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', gap: '12px', padding: '20px 0',
        }}>
          {pages.map((page) => (
            <div
              key={page.pageNumber}
              data-page={page.pageNumber}
              style={{
                position: 'relative',
                background: '#fff',
                boxShadow: '0 1px 6px rgba(0,0,0,0.1)',
              }}
            >
              <canvas
                ref={(el) => setCanvasRef(page.pageNumber, el)}
                style={{ display: 'block' }}
              />
              <div style={{
                position: 'absolute', bottom: '6px', right: '8px',
                fontSize: '10px', color: '#999',
                background: 'rgba(255,255,255,0.8)', padding: '1px 5px',
                borderRadius: '3px',
              }}>
                {page.pageNumber} / {pageCount}
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }
)

export default PdfContinuousViewer
