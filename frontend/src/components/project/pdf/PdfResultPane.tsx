import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import type { ExtractionResult } from '../../../types'

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
}

// 虚拟滚动常量
const ITEM_HEIGHT = 140
const OVERSCAN = 5

function itemsToText(items: TextItem[]): string {
  if (items.length === 0) return ''
  const sorted = [...items].sort((a, b) => {
    const dy = a.y - b.y
    if (Math.abs(dy) > 3) return dy
    return a.x - b.x
  })
  const lines: string[][] = []
  let currentLine: string[] = []
  let currentY = sorted[0].y
  for (const item of sorted) {
    if (Math.abs(item.y - currentY) > 6) {
      if (currentLine.length > 0) lines.push(currentLine)
      currentLine = [item.str]
      currentY = item.y
    } else {
      currentLine.push(item.str)
    }
  }
  if (currentLine.length > 0) lines.push(currentLine)
  return lines.map(line => line.join(' ').trim()).join('\n')
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

function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export default function PdfResultPane({
  currentPage,
  currentTextItems,
  currentTextTotal,
  detections,
  selectedDetection,
  onSelectDetection,
  onScrollToDetection,
  confidenceThreshold = 0.3,
}: Props) {
  const textContent = itemsToText(currentTextItems)
  const containerRef = useRef<HTMLDivElement>(null)
  const prevPageRef = useRef(currentPage)

  const groupedDetections = useMemo(() => {
    if (detections.length === 0) return []
    const filtered = detections.filter(d => d.composite_conf >= confidenceThreshold)
    const sorted = filtered.map((d, i) => ({ ...d, _originalIndex: i }))
    sorted.sort((a, b) => {
      const ay = a.bbox_pdf?.[1] ?? 0
      const by = b.bbox_pdf?.[1] ?? 0
      return ay - by
    })
    return sorted
  }, [detections, confidenceThreshold])

  useEffect(() => {
    if (currentPage !== prevPageRef.current) {
      prevPageRef.current = currentPage
      if (containerRef.current) {
        containerRef.current.scrollTop = 0
      }
    }
  }, [currentPage])

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
            {groupedDetections.length > 0 && (
              <span className="pdf-result-stat pdf-result-stat-mol">{groupedDetections.length} 分子</span>
            )}
          </div>
        </div>
      </div>

      <div className="pdf-result-content" ref={containerRef}>
        {/* 文本内容区 */}
        <div className="pdf-result-section">
          <div className="pdf-result-section-header">文本内容</div>
          {textContent ? (
            <pre className="pdf-result-text-pre">{textContent}</pre>
          ) : (
            <div className="pdf-result-empty">当前页无文本内容</div>
          )}
        </div>

        {/* 分子识别区 */}
        <div className="pdf-result-section">
          <div className="pdf-result-section-header">
            分子识别
            {groupedDetections.length > 0 && (
              <span className="pdf-result-section-count">{groupedDetections.length}</span>
            )}
          </div>
          {groupedDetections.length === 0 ? (
            <div className="pdf-result-empty">当前页未检测到分子</div>
          ) : (
            <MoleculeVirtualList
              detections={groupedDetections}
              selectedDetection={selectedDetection}
              onSelect={handleMoleculeClick}
              onScrollToDetection={onScrollToDetection}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// 虚拟滚动分子列表
// ============================================================================

interface VirtualListProps {
  detections: (ExtractionResult & { _originalIndex: number })[]
  selectedDetection: number | null
  onSelect: (mol: ExtractionResult, index: number) => void
  onScrollToDetection?: (detection: ExtractionResult) => void
}

function MoleculeVirtualList({
  detections,
  selectedDetection,
  onSelect,
  onScrollToDetection,
}: VirtualListProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scrollTop, setScrollTop] = useState(0)

  const handleScroll = useCallback(() => {
    if (containerRef.current) {
      setScrollTop(containerRef.current.scrollTop)
    }
  }, [])

  const startIndex = Math.max(0, Math.floor(scrollTop / ITEM_HEIGHT) - OVERSCAN)
  const endIndex = Math.min(
    detections.length,
    Math.ceil((scrollTop + (containerRef.current?.clientHeight || 600)) / ITEM_HEIGHT) + OVERSCAN
  )
  const visibleItems = detections.slice(startIndex, endIndex)

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="pdf-molecule-virtual-list"
    >
      <div
        className="pdf-molecule-virtual-spacer"
        style={{ height: detections.length * ITEM_HEIGHT }}
      >
        {visibleItems.map((mol, idx) => {
          const actualIndex = startIndex + idx
          const offset = actualIndex * ITEM_HEIGHT
          return (
            <div
              key={mol._originalIndex}
              className="pdf-molecule-virtual-item"
              style={{ top: offset }}
            >
              <MoleculeCard
                mol={mol}
                isSelected={selectedDetection === mol._originalIndex}
                onClick={() => onSelect(mol, mol._originalIndex)}
                onLocate={onScrollToDetection ? () => onScrollToDetection(mol) : undefined}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ============================================================================
// 分子卡片组件
// ============================================================================

interface MoleculeCardProps {
  mol: ExtractionResult & { _originalIndex: number }
  isSelected: boolean
  onClick: () => void
  onLocate?: () => void
}

function MoleculeCard({ mol, isSelected, onClick, onLocate }: MoleculeCardProps) {
  return (
    <div
      className={`pdf-molecule-card ${isSelected ? 'selected' : ''}`}
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
        <div className="pdf-molecule-smiles-row">
          <code className="pdf-molecule-smiles-value">
            {mol.esmiles || mol.smiles || '-'}
          </code>
          {mol.smiles && mol.esmiles && mol.smiles !== mol.esmiles && (
            <code className="pdf-molecule-smiles-alt" title="标准 SMILES">
              {mol.smiles}
            </code>
          )}
        </div>
      </div>

      {mol.context_text && (
        <div className="pdf-molecule-coref">
          <div className="pdf-molecule-coref-header">
            <span className="pdf-molecule-coref-label">上下文关联</span>
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
          <p className="pdf-molecule-coref-text">
            {highlightContext(mol.context_text, mol.name)}
          </p>
        </div>
      )}

      <div className="pdf-molecule-meta">
        <span className="pdf-molecule-source">
          {mol.source === 'image' ? '图像识别' : mol.source === 'text' ? '文本提取' : '手动添加'}
        </span>
        {mol.bbox_pdf && (
          <span className="pdf-molecule-location">
            页内位置
          </span>
        )}
      </div>
    </div>
  )
}
