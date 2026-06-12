import { useMemo, useState } from 'react'
import type { ExtractionResult, DetectionBox } from '../types'

interface Props {
  /** MolDet 检测结果列表 */
  detections: ExtractionResult[]
  /** 渲染后的 canvas/页面宽度（CSS 像素） */
  renderWidth: number
  /** 渲染后的 canvas/页面高度（CSS 像素） */
  renderHeight: number
  /** 页面原始高度（PDF points, 72 DPI） */
  originalHeight: number
  /** 缩放比例 */
  scale: number
  /** 选中的检测索引 */
  selectedIndex?: number
  /** 选中检测回调（用于已识别条目） */
  onSelect?: (index: number) => void
  /** 触发完整识别（用于 quick-scan bbox-only 条目） */
  onRecognize?: () => void
  /** 是否正在识别中 */
  isRecognizing?: boolean
}

/** 将 PDF 坐标（左下角原点）转换为 CSS 像素坐标（左上角原点） */
function pdfToCss(
  bbox: [number, number, number, number],
  pageHeightPts: number,
  scale: number,
): { x: number; y: number; w: number; h: number } {
  const [x1, y1, x2, y2] = bbox
  const pdfW = x2 - x1
  const pdfH = y2 - y1
  // PDF 坐标系：左下角原点，Y 向上
  // CSS 坐标系：左上角原点，Y 向下
  const cssX = x1 * scale
  const cssY = (pageHeightPts - y2) * scale
  const cssW = pdfW * scale
  const cssH = pdfH * scale
  return { x: cssX, y: cssY, w: cssW, h: cssH }
}

/** 置信度颜色 */
function confColor(conf: number): string {
  if (conf >= 0.8) return 'var(--success)'
  if (conf >= 0.5) return 'var(--warning)'
  return 'var(--danger)'
}

export default function MoleculeOverlay({
  detections,
  renderWidth,
  renderHeight,
  originalHeight,
  scale,
  selectedIndex,
  onSelect,
  onRecognize,
  isRecognizing,
}: Props) {
  // 将 PDF bbox 转换为 CSS 像素坐标
  const boxes: DetectionBox[] = useMemo(() => {
    return detections
      .filter(d => d.bbox_pdf != null)
      .map((d) => {
        const bbox = pdfToCss(d.bbox_pdf!, originalHeight, scale)
        return {
          x1: bbox.x,
          y1: bbox.y,
          x2: bbox.x + bbox.w,
          y2: bbox.y + bbox.h,
          conf: d.composite_conf,
          result: d,
        }
      })
  }, [detections, originalHeight, scale])

  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null)

  if (boxes.length === 0) return null

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: renderWidth,
        height: renderHeight,
        pointerEvents: 'none',
        zIndex: 2,
      }}
    >
      {boxes.map((box, i) => {
        const isSelected = selectedIndex === i
        const isHovered = hoveredIdx === i
        const color = confColor(box.conf)
        const boxW = box.x2 - box.x1
        const boxH = box.y2 - box.y1
        const smi = box.result?.esmiles || ''
        const isQuickScan = (box.result as unknown as { is_quick_scan?: boolean })?.is_quick_scan
        const confPct = Math.round(box.conf * 100)
        const ctx = box.result?.context_text || ''

        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: box.x1,
              top: box.y1,
              width: boxW,
              height: boxH,
              border: `2px ${isQuickScan ? 'dashed' : 'solid'} ${color}`,
              borderRadius: '3px',
              background: isSelected ? 'rgba(59,130,246,0.1)' : 'transparent',
              cursor: isRecognizing ? 'wait' : 'pointer',
              pointerEvents: isRecognizing ? 'none' : 'auto',
              opacity: isQuickScan ? 0.85 : 1,
              transition: 'all 0.15s',
            }}
            onClick={() => {
              if (isQuickScan) {
                onRecognize?.()
              } else {
                onSelect?.(i)
              }
            }}
            onMouseEnter={() => setHoveredIdx(i)}
            onMouseLeave={() => setHoveredIdx(null)}
          >
            {/* 标签：SMILES + 置信度 */}
            <div style={{
              position: 'absolute',
              top: -24,
              left: 0,
              display: 'flex',
              gap: '4px',
              alignItems: 'center',
              whiteSpace: 'nowrap',
              fontSize: '10px',
              fontFamily: 'monospace',
              pointerEvents: 'none',
            }}>
              <span style={{
                background: color,
                color: '#fff',
                padding: '1px 5px',
                borderRadius: '3px',
                fontWeight: 600,
                fontSize: '9px',
              }}>
                {confPct}%
              </span>
              {isQuickScan ? (
                <span style={{
                  background: 'var(--bg-surface)',
                  color: 'var(--text-secondary)',
                  padding: '1px 5px',
                  borderRadius: '3px',
                  border: '1px solid var(--border)',
                  fontSize: '9px',
                }}>
                  未识别
                </span>
              ) : smi ? (
                <span style={{
                  background: 'var(--bg-surface)',
                  color: 'var(--text-secondary)',
                  padding: '1px 5px',
                  borderRadius: '3px',
                  border: '1px solid var(--border)',
                  maxWidth: boxW,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}>
                  {smi.length > 30 ? smi.slice(0, 30) + '...' : smi}
                </span>
              ) : null}
            </div>
            {/* Hover tooltip: 上下文文本 */}
            {isHovered && ctx && (
              <div style={{
                position: 'absolute',
                top: boxH + 6,
                left: 0,
                maxWidth: '300px',
                padding: '6px 10px',
                background: 'var(--bg-elevated, #1e1e1e)',
                color: 'var(--text-secondary, #ccc)',
                fontSize: '10px',
                lineHeight: 1.4,
                borderRadius: '6px',
                border: '1px solid var(--border)',
                boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                zIndex: 100,
                pointerEvents: 'none',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {ctx.length > 200 ? ctx.slice(0, 200) + '...' : ctx}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
