import { useEffect, useRef, useState, useCallback } from 'react'
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
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

interface Props {
  url: string
  scale?: number
  onPageChange?: (page: number) => void
  onPageCount?: (count: number) => void
}

interface PageData {
  pageNumber: number
  width: number
  height: number
}

export default function PdfContinuousViewer({
  url,
  scale = 1.5,
  onPageChange,
  onPageCount,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pageCount, setPageCount] = useState(0)
  const [pages, setPages] = useState<PageData[]>([])
  const [visiblePages, setVisiblePages] = useState<Set<number>>(new Set())
  const pdfDocRef = useRef<PDFDocumentProxy | null>(null)
  const canvasRefs = useRef<Map<number, HTMLCanvasElement>>(new Map())
  const renderedPages = useRef<Set<number>>(new Set())
  const onPageChangeRef = useRef(onPageChange)
  const onPageCountRef = useRef(onPageCount)
  onPageChangeRef.current = onPageChange
  onPageCountRef.current = onPageCount

  // Load document
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setPages([])
    setVisiblePages(new Set())
    renderedPages.current.clear()

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

    return () => { cancelled = true }
  }, [url, scale])

  // Render visible pages
  useEffect(() => {
    const doc = pdfDocRef.current
    if (!doc) return

    visiblePages.forEach(async (pageNum) => {
      if (renderedPages.current.has(pageNum)) return
      renderedPages.current.add(pageNum)

      const canvas = canvasRefs.current.get(pageNum)
      if (!canvas) return

      try {
        const page = await doc.getPage(pageNum)
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
        await page.render({
          canvasContext: ctx,
          viewport: page.getViewport({ scale }),
        }).promise
      } catch (e) {
        console.error(`Render page ${pageNum} failed:`, e)
      }
    })
  }, [visiblePages, scale])

  // IntersectionObserver to track visible pages
  useEffect(() => {
    const container = containerRef.current
    if (!container || pages.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        const newVisible = new Set<number>()
        entries.forEach((entry) => {
          const pageNum = Number((entry.target as HTMLElement).dataset.page)
          if (entry.isIntersecting) {
            newVisible.add(pageNum)
          }
        })
        setVisiblePages(newVisible)

        // Report the top-most visible page as current
        const sorted = Array.from(newVisible).sort((a, b) => a - b)
        if (sorted.length > 0) {
          onPageChangeRef.current?.(sorted[0])
        }
      },
      { root: container, threshold: 0.1 }
    )

    const pageEls = container.querySelectorAll('[data-page]')
    pageEls.forEach((el) => observer.observe(el))

    return () => observer.disconnect()
  }, [pages])

  const setCanvasRef = useCallback((pageNum: number, el: HTMLCanvasElement | null) => {
    if (el) {
      canvasRefs.current.set(pageNum, el)
    } else {
      canvasRefs.current.delete(pageNum)
      renderedPages.current.delete(pageNum)
    }
  }, [])

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
    <div ref={containerRef} style={{ width: '100%', height: '100%', overflowY: 'auto' }}>
      <div style={{
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', gap: '16px', padding: '20px 0',
      }}>
        {pages.map((page) => (
          <div
            key={page.pageNumber}
            data-page={page.pageNumber}
            style={{
              position: 'relative',
              background: '#fff',
              boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
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
