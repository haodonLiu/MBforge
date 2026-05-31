import { useEffect, useRef, useState, useCallback } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import * as pdfjsLib from 'pdfjs-dist'

// 配置 pdf.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.mjs',
  import.meta.url,
).toString()

// ---- 模块级文档缓存：避免重复下载 ----
const docCache = new Map<string, Promise<PDFDocumentProxy>>()

function getCachedDoc(url: string): Promise<PDFDocumentProxy> {
  let promise = docCache.get(url)
  if (!promise) {
    promise = pdfjsLib.getDocument(url).promise
    docCache.set(url, promise)
  }
  return promise
}

interface Props {
  /** PDF 文件 URL */
  url: string
  /** 当前页码（1-indexed） */
  pageNumber: number
  /** 缩放比例 */
  scale?: number
  /** 是否生成页面图片 data URL（仅检测模式开启） */
  generateImage?: boolean
  /** 页面渲染完成回调 */
  onPageRendered?: (info: {
    pageNumber: number
    width: number
    height: number
    originalWidth: number
    originalHeight: number
    scale: number
  }) => void
  /** 页面图片 data URL 回调 */
  onImageReady?: (pageNumber: number, dataUrl: string) => void
  className?: string
  style?: React.CSSProperties
}

export default function PdfCanvas({
  url,
  pageNumber,
  scale = 1.5,
  generateImage = false,
  onPageRendered,
  onImageReady,
  className,
  style,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const totalPagesRef = useRef(0)
  const [totalPages, setTotalPages] = useState(0)
  const pdfDocRef = useRef<PDFDocumentProxy | null>(null)
  // 用 ref 追踪回调，避免 re-render cascade
  const onPageRenderedRef = useRef(onPageRendered)
  const onImageReadyRef = useRef(onImageReady)
  const generateImageRef = useRef(generateImage)
  onPageRenderedRef.current = onPageRendered
  onImageReadyRef.current = onImageReady
  generateImageRef.current = generateImage

  // 加载 PDF 文档（带缓存）
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
      })
      .catch(e => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load PDF')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [url])

  // 渲染当前页 — 依赖只有 pageNumber 和 scale
  const renderPage = useCallback(async () => {
    const doc = pdfDocRef.current
    const canvas = canvasRef.current
    if (!doc || !canvas) return

    try {
      const page = await doc.getPage(pageNumber)
      const viewport = page.getViewport({ scale })
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      canvas.width = viewport.width
      canvas.height = viewport.height
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      await page.render({ canvasContext: ctx, viewport }).promise

      const originalViewport = page.getViewport({ scale: 1 })
      onPageRenderedRef.current?.({
        pageNumber,
        width: viewport.width,
        height: viewport.height,
        originalWidth: originalViewport.width,
        originalHeight: originalViewport.height,
        scale,
      })

      // 仅在检测模式生成 data URL（避免读取模式的 CPU 开销）
      if (generateImageRef.current) {
        onImageReadyRef.current?.(pageNumber, canvas.toDataURL('image/png'))
      }
    } catch (e) {
      console.error('PDF render error:', e)
    }
  }, [pageNumber, scale])

  useEffect(() => {
    if (!loading && !error) renderPage()
  }, [loading, error, renderPage])

  return (
    <div className={className} style={{ position: 'relative', ...style }}>
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
      {totalPages > 0 && (
        <div style={{
          position: 'absolute', bottom: '8px', left: '50%',
          transform: 'translateX(-50%)',
          fontSize: '11px', color: 'var(--text-muted)',
          background: 'var(--bg-surface)', padding: '2px 8px',
          borderRadius: '4px', border: '1px solid var(--border)',
        }}>
          {pageNumber} / {totalPages}
        </div>
      )}
    </div>
  )
}
