import { useMemo, useRef, useEffect, useCallback, useState } from 'react'
import type { ExtractionResult } from '../../../types'
import type { OcrBlock } from '../../../api/http/pdf'

interface TextItem {
  str: string
  x: number
  y: number
  width: number
  height: number
}

interface Props {
  currentPage: number
  currentTextItems: TextItem[]
  currentTextTotal: number
  detections: ExtractionResult[]
  selectedDetection: number | null
  onSelectDetection: (index: number | null) => void
  onScrollToDetection?: (detection: ExtractionResult) => void
  confidenceThreshold?: number
  /** 当前文档的 OCR 布局块（用于按 OCR 段落边界正确拼接文本） */
  ocrBlocks?: OcrBlock[]
}

// ============================================================================
// 数据结构：统一内容流
// ============================================================================

interface TextBlock {
  type: 'text'
  sortY: number
  text: string
}

interface MoleculeBlock {
  type: 'molecule'
  sortY: number
  mol: ExtractionResult & { _originalIndex: number }
  originalIndex: number
}

type ContentBlock = TextBlock | MoleculeBlock

// 文本行高度估算
const LINE_HEIGHT = 28
// 分子卡片高度
const MOL_CARD_HEIGHT = 120
// 虚拟滚动 overscan
const OVERSCAN = 8

// ============================================================================
// 工具函数
// ============================================================================

function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function highlightContext(text: string, name: string): React.ReactNode {
  if (!name || !text) return text
  const parts = text.split(new RegExp(`(${escapeRegex(name)})`, 'gi'))
  return parts.map((part, i) =>
    part.toLowerCase() === name.toLowerCase()
      ? <mark key={i} className="pdf-highlight">{part}</mark>
      : part
  )
}

/**
 * 把 text items 按 y 坐标聚合成行（OCR 感知）。
 *
 * - 有当前页的 OCR text blocks：按 OCR 块的 bbox 把 items 归到对应段落（语义边界 = 段落），
 *   段内按 y 阈值分行。OCR 块作为更强的语义边界，避免标题/正文/页眉被错误合并。
 * - 无 OCR blocks：fallback 到纯 y 阈值分行启发式（与旧版一致）。
 *
 * 坐标语义：PDF text item.y 是 PDF bottom-left origin 的 baseline；OcrBlock.bbox
 * 是 backend 已做 top-left → bottom-left 翻转后的 PDF points bottom-left origin
 * （见 mbforge-pipeline/src/pdf/mineru.rs::parse_layout_json）。
 */
function groupTextLines(
  items: TextItem[],
  ocrTextBlocks: OcrBlock[] = [],
): { text: string; y: number }[] {
  if (items.length === 0) return []

  if (ocrTextBlocks.length === 0) {
    // 无 OCR：纯 y 排序 + 阈值分行
    return groupByYThreshold(items)
  }

  // OCR 感知：按 OCR text block bbox 把 items 归段，再段内分行
  // bbox[1] = 块底 y（PDF bottom-left origin）；越大越靠上 → 降序 = 上→下
  const sortedBlocks = [...ocrTextBlocks].sort((a, b) => b.bbox[1] - a.bbox[1])
  const used = new Set<TextItem>()
  const lines: { text: string; y: number }[] = []

  for (const block of sortedBlocks) {
    const [x1, y1, x2, y2] = block.bbox
    const inBlock = items.filter((it) => {
      if (used.has(it)) return false
      const cx = it.x + it.width / 2
      const cy = it.y
      // 边界 ±3pt 容差，避免边缘 item 漏分到相邻块
      return cx >= x1 - 3 && cx <= x2 + 3 && cy >= y1 - 3 && cy <= y2 + 3
    })
    if (inBlock.length === 0) continue
    inBlock.forEach((it) => used.add(it))
    for (const line of groupByYThreshold(inBlock)) {
      lines.push(line)
    }
  }

  // 剩余 items（不在任何 OCR 块内的）：按 y 排序 + 阈值分行，追加在末尾
  const leftovers = items.filter((it) => !used.has(it))
  if (leftovers.length > 0) {
    for (const line of groupByYThreshold(leftovers)) {
      lines.push(line)
    }
  }

  // 整体按 y 降序（顶部优先）
  lines.sort((a, b) => b.y - a.y)
  return lines
}

/** 纯 y 排序 + 阈值分行的兜底实现（item.y 差 > 6pt 视为新行） */
function groupByYThreshold(items: TextItem[]): { text: string; y: number }[] {
  if (items.length === 0) return []
  const sorted = [...items].sort((a, b) => {
    const dy = b.y - a.y
    if (Math.abs(dy) > 6) return dy
    return a.x - b.x
  })
  const lines: { text: string; y: number }[] = []
  let currentParts: string[] = []
  let currentY = sorted[0].y
  for (const item of sorted) {
    if (Math.abs(item.y - currentY) > 6) {
      if (currentParts.length > 0) {
        lines.push({ text: currentParts.join(' ').trim(), y: currentY })
      }
      currentParts = [item.str]
      currentY = item.y
    } else {
      currentParts.push(item.str)
    }
  }
  if (currentParts.length > 0) {
    lines.push({ text: currentParts.join(' ').trim(), y: currentY })
  }
  return lines.filter(l => l.text.length > 0)
}

/** 将文本行和分子检测按 y 坐标交错排列 */
function buildContentStream(
  textItems: TextItem[],
  detections: (ExtractionResult & { _originalIndex: number })[],
  ocrTextBlocks: OcrBlock[] = [],
): ContentBlock[] {
  const lines = groupTextLines(textItems, ocrTextBlocks)
  const blocks: ContentBlock[] = []

  for (const line of lines) {
    blocks.push({ type: 'text', sortY: line.y, text: line.text })
  }

  for (const mol of detections) {
    const y = mol.bbox_pdf?.[1] ?? 0
    blocks.push({ type: 'molecule', sortY: y, mol, originalIndex: mol._originalIndex })
  }

  // 按 y 降序排列（PDF 坐标系：y 越大越靠页面顶部）
  blocks.sort((a, b) => b.sortY - a.sortY)
  return blocks
}

/** 估算每个 block 的像素高度 */
function estimateBlockHeight(block: ContentBlock): number {
  if (block.type === 'text') {
    const lineCount = Math.max(1, Math.ceil(block.text.length / 50))
    return lineCount * LINE_HEIGHT + 12 // padding
  }
  return MOL_CARD_HEIGHT
}

// ============================================================================
// 主组件
// ============================================================================

export default function PdfResultPane({
  currentPage,
  currentTextItems,
  currentTextTotal,
  detections,
  selectedDetection,
  onSelectDetection,
  onScrollToDetection,
  confidenceThreshold = 0.3,
  ocrBlocks = [],
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const prevPageRef = useRef(currentPage)
  const [scrollTop, setScrollTop] = useState(0)

  const filteredDetections = useMemo(() => {
    if (detections.length === 0) return []
    const filtered = detections.filter(d => d.composite_conf >= confidenceThreshold)
    return filtered.map((d, i) => ({ ...d, _originalIndex: i }))
  }, [detections, confidenceThreshold])

  // 当前页的 OCR text blocks（用于按语义段落边界拼接文本）
  const currentPageOcrTextBlocks = useMemo(
    () => ocrBlocks.filter(b => b.page === currentPage && b.block_type === 'text'),
    [ocrBlocks, currentPage],
  )

  const contentBlocks = useMemo(
    () => buildContentStream(currentTextItems, filteredDetections, currentPageOcrTextBlocks),
    [currentTextItems, filteredDetections, currentPageOcrTextBlocks],
  )

  // 预计算每个 block 的累计高度
  const blockOffsets = useMemo(() => {
    const offsets: number[] = []
    let total = 0
    for (const block of contentBlocks) {
      offsets.push(total)
      total += estimateBlockHeight(block)
    }
    return { offsets, totalHeight: total }
  }, [contentBlocks])

  useEffect(() => {
    if (currentPage !== prevPageRef.current) {
      prevPageRef.current = currentPage
      setScrollTop(0)
      if (containerRef.current) {
        containerRef.current.scrollTop = 0
      }
    }
  }, [currentPage])

  const handleScroll = useCallback(() => {
    if (containerRef.current) {
      setScrollTop(containerRef.current.scrollTop)
    }
  }, [])

  // 虚拟滚动：计算可见范围
  const containerHeight = containerRef.current?.clientHeight || 600
  const startIdx = Math.max(0,
    blockOffsets.offsets.findIndex(o => o + estimateBlockHeight(contentBlocks[blockOffsets.offsets.indexOf(o)]) > scrollTop) - OVERSCAN
  )
  const safeStartIdx = startIdx < 0 ? 0 : startIdx
  let endIdx = safeStartIdx
  while (endIdx < contentBlocks.length && blockOffsets.offsets[endIdx] < scrollTop + containerHeight + 200) {
    endIdx++
  }
  endIdx = Math.min(contentBlocks.length, endIdx + OVERSCAN)

  const handleMoleculeClick = (mol: ExtractionResult, index: number) => {
    onSelectDetection(selectedDetection === index ? null : index)
    if (onScrollToDetection) {
      onScrollToDetection(mol)
    }
  }

  return (
    <div className="pdf-result-pane">
      <div className="pdf-result-header">
        <div className="pdf-result-header-top">
          <div className="pdf-result-title">
            <span className="pdf-result-label">识别结果</span>
            <span className="pdf-result-page">第 {currentPage} 页</span>
          </div>
          <div className="pdf-result-stats">
            {currentTextTotal > 0 && (
              <span className="pdf-result-stat">{currentTextTotal} 字符</span>
            )}
            {filteredDetections.length > 0 && (
              <span className="pdf-result-stat pdf-result-stat-mol">{filteredDetections.length} 分子</span>
            )}
          </div>
        </div>
      </div>

      <div
        className="pdf-result-content"
        ref={containerRef}
        onScroll={handleScroll}
      >
        {contentBlocks.length === 0 ? (
          <div className="pdf-result-empty">当前页无内容</div>
        ) : (
          <div className="pdf-unified-stream" style={{ height: blockOffsets.totalHeight, position: 'relative' }}>
            {contentBlocks.slice(safeStartIdx, endIdx).map((block, i) => {
              const idx = safeStartIdx + i
              const top = blockOffsets.offsets[idx]
              if (block.type === 'text') {
                return (
                  <div
                    key={`t-${idx}`}
                    className="pdf-stream-text"
                    style={{ position: 'absolute', top, left: 0, right: 0 }}
                  >
                    {block.text}
                  </div>
                )
              }
              return (
                <div
                  key={`m-${block.originalIndex}`}
                  className="pdf-stream-mol"
                  style={{ position: 'absolute', top, left: 0, right: 0 }}
                >
                  <MoleculeCardInline
                    mol={block.mol}
                    isSelected={selectedDetection === block.originalIndex}
                    onClick={() => handleMoleculeClick(block.mol, block.originalIndex)}
                    onLocate={onScrollToDetection ? () => onScrollToDetection(block.mol) : undefined}
                  />
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// 内联分子卡片（紧凑版）
// ============================================================================

interface MoleculeCardInlineProps {
  mol: ExtractionResult & { _originalIndex: number }
  isSelected: boolean
  onClick: () => void
  onLocate?: () => void
}

function MoleculeCardInline({ mol, isSelected, onClick, onLocate }: MoleculeCardInlineProps) {
  return (
    <div
      className={`pdf-molecule-card inline ${isSelected ? 'selected' : ''}`}
      onClick={onClick}
    >
      <div className="pdf-molecule-header">
        <div className="pdf-molecule-id">
          <span className="pdf-molecule-index">#{mol._originalIndex + 1}</span>
          {mol.name && <span className="pdf-molecule-name-tag">{mol.name}</span>}
        </div>
        <span className="pdf-molecule-confidence">
          {Math.round(mol.composite_conf * 100)}%
        </span>
      </div>

      <div className="pdf-molecule-smiles">
        <code className="pdf-molecule-smiles-value">
          {mol.esmiles || mol.smiles || '-'}
        </code>
      </div>

      {mol.context_text && (
        <div className="pdf-molecule-coref">
          <p className="pdf-molecule-coref-text">
            {highlightContext(mol.context_text, mol.name)}
          </p>
          {mol.bbox_pdf && onLocate && (
            <button
              className="pdf-molecule-jump-btn"
              onClick={(e) => {
                e.stopPropagation()
                onLocate()
              }}
              title="跳转到 PDF 位置"
            >
              定位
            </button>
          )}
        </div>
      )}
    </div>
  )
}
