import { useMemo, useRef, useEffect } from 'react'
import type { OcrBlock } from '../api/tauri/pdf'

interface Props {
  blocks: OcrBlock[]
  currentPage: number
  selectedIndex: number | null
  hoveredIndex: number | null
  onSelect: (index: number) => void
  onClose: () => void
}

/** 块类型颜色映射（与 OcrOverlay 一致） */
function blockTypeColor(type: string): string {
  switch (type) {
    case 'text': return '#2563eb'
    case 'image': return '#16a34a'
    case 'table': return '#f59e0b'
    case 'formula': return '#9333ea'
    case 'chart': return '#dc2626'
    case 'header': return '#64748b'
    case 'footer': return '#64748b'
    case 'seal': return '#0891b2'
    default: return '#6b7280'
  }
}

/** 块类型中文标签 */
function blockTypeLabel(type: string): string {
  const map: Record<string, string> = {
    text: '文本', image: '图片', table: '表格',
    formula: '公式', chart: '图表', header: '页眉',
    footer: '页脚', seal: '印章',
  }
  return map[type] || type
}

export default function OcrResultPanel({
  blocks,
  currentPage,
  selectedIndex,
  hoveredIndex,
  onSelect,
  onClose,
}: Props) {
  const listRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<Map<number, HTMLDivElement>>(new Map())

  // 只显示当前页的块
  const pageBlocks = useMemo(() => {
    return blocks
      .map((block, i) => ({ block, originalIndex: i }))
      .filter(({ block }) => block.page === currentPage)
  }, [blocks, currentPage])

  // 选中项自动滚动到视图
  useEffect(() => {
    if (selectedIndex == null) return
    const el = itemRefs.current.get(selectedIndex)
    if (el && listRef.current) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [selectedIndex])

  return (
    <div style={{
      width: '300px',
      borderLeft: '1px solid var(--border)',
      background: 'var(--bg-surface)',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      flexShrink: 0,
    }}>
      {/* 头部 */}
      <div style={{
        padding: '8px 12px',
        borderBottom: '1px solid var(--border)',
        fontSize: '11px',
        fontWeight: 600,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span>OCR 结果 (第 {currentPage} 页, {pageBlocks.length} 块)</span>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--text-muted)',
            fontSize: '14px',
            lineHeight: 1,
          }}
        >✕</button>
      </div>

      {/* 块列表 */}
      <div
        ref={listRef}
        style={{
          flex: 1,
          overflow: 'auto',
          padding: '8px',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
        }}
      >
        {pageBlocks.length === 0 && (
          <div style={{
            fontSize: '11px',
            color: 'var(--text-muted)',
            textAlign: 'center',
            padding: '20px 8px',
          }}>
            当前页没有 OCR 块数据
          </div>
        )}
        {pageBlocks.map(({ block, originalIndex }) => {
          const isSelected = selectedIndex === originalIndex
          const isHovered = hoveredIndex === originalIndex
          const color = blockTypeColor(block.block_type)
          const content = block.content || ''

          return (
            <div
              key={originalIndex}
              ref={(el) => {
                if (el) itemRefs.current.set(originalIndex, el)
                else itemRefs.current.delete(originalIndex)
              }}
              onClick={() => onSelect(originalIndex)}
              style={{
                padding: '8px 10px',
                borderRadius: '6px',
                border: `1px solid ${isSelected ? color : 'var(--border)'}`,
                background: isSelected ? `${color}10` : isHovered ? 'var(--bg-base)' : 'transparent',
                cursor: 'pointer',
                transition: 'all 0.12s ease',
              }}
            >
              {/* 类型标签 + 索引 */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                marginBottom: '4px',
              }}>
                <span style={{
                  background: color,
                  color: '#fff',
                  padding: '1px 5px',
                  borderRadius: '3px',
                  fontSize: '9px',
                  fontWeight: 600,
                }}>
                  {blockTypeLabel(block.block_type)}
                </span>
                <span style={{
                  fontSize: '10px',
                  color: 'var(--text-muted)',
                  fontFamily: 'monospace',
                }}>
                  #{block.index}
                </span>
              </div>

              {/* 内容预览 */}
              {content && (
                <div style={{
                  fontSize: '11px',
                  color: 'var(--text-secondary)',
                  lineHeight: 1.5,
                  wordBreak: 'break-word',
                }}>
                  {content.length > 120 ? content.slice(0, 120) + '...' : content}
                </div>
              )}
              {!content && (
                <div style={{
                  fontSize: '10px',
                  color: 'var(--text-muted)',
                  fontStyle: 'italic',
                }}>
                  无文本内容
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
