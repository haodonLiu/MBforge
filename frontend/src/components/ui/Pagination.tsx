import { useMemo } from 'react'

export interface PaginationProps {
  /** 当前页（1-based）*/
  current: number
  /** 总页数 */
  total: number
  /** 每页大小（用于显示）*/
  pageSize?: number
  /** 总条数（用于显示）*/
  totalItems?: number
  /** 页码变化回调 */
  onChange: (page: number) => void
  /** 快速跳转 */
  showQuickJumper?: boolean
  /** 显示总数 */
  showTotal?: boolean
  /** 兄弟节点数（默认 1）*/
  siblingCount?: number
  size?: 'sm' | 'md' | 'lg'
  style?: React.CSSProperties
  className?: string
}

const sizeMap = {
  sm: { minWidth: 24, height: 24, fontSize: 11, padding: '0 6px' },
  md: { minWidth: 32, height: 32, fontSize: 12, padding: '0 10px' },
  lg: { minWidth: 40, height: 40, fontSize: 14, padding: '0 12px' },
}

/**
 * 计算分页器中显示的页码列表（含省略号）。
 *
 * 例如 total=10, current=5, siblingCount=1 → [1, '...', 4, 5, 6, '...', 10]
 */
function getPageNumbers(current: number, total: number, siblingCount: number): (number | 'ellipsis')[] {
  // 总页数 <= 兄弟节点 + 5，全部显示
  const totalNumbers = siblingCount * 2 + 5
  if (total <= totalNumbers) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }

  const leftSibling = Math.max(current - siblingCount, 1)
  const rightSibling = Math.min(current + siblingCount, total)

  const showLeftEllipsis = leftSibling > 2
  const showRightEllipsis = rightSibling < total - 1

  const items: (number | 'ellipsis')[] = [1]

  if (showLeftEllipsis) {
    items.push('ellipsis')
  } else {
    for (let i = 2; i < leftSibling; i++) items.push(i)
  }

  for (let i = leftSibling; i <= rightSibling; i++) {
    if (i !== 1 && i !== total) items.push(i)
  }

  if (showRightEllipsis) {
    items.push('ellipsis')
  } else {
    for (let i = rightSibling + 1; i < total; i++) items.push(i)
  }

  if (total !== 1) items.push(total)

  return items
}

/**
 * Pagination 分页器。
 *
 * 支持页码跳转、省略号、当前页高亮。
 */
export default function Pagination({
  current,
  total,
  pageSize,
  totalItems,
  onChange,
  showQuickJumper = false,
  showTotal = false,
  siblingCount = 1,
  size = 'md',
  style,
  className,
}: PaginationProps) {
  const sizeStyle = sizeMap[size]
  const pages = useMemo(
    () => getPageNumbers(current, total, siblingCount),
    [current, total, siblingCount],
  )

  const canPrev = current > 1
  const canNext = current < total

  const renderButton = (
    key: string,
    content: React.ReactNode,
    onClick: () => void,
    isActive = false,
    isDisabled = false,
  ) => (
    <button
      key={key}
      type="button"
      onClick={onClick}
      disabled={isDisabled}
      style={{
        ...sizeStyle,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: isActive ? 'var(--accent)' : 'var(--bg-surface)',
        color: isActive ? 'white' : isDisabled ? 'var(--text-muted)' : 'var(--text-secondary)',
        border: `1px solid ${isActive ? 'var(--accent)' : 'var(--border)'}`,
        borderRadius: 6,
        cursor: isDisabled ? 'not-allowed' : 'pointer',
        opacity: isDisabled ? 0.5 : 1,
        transition: 'all 0.15s',
        fontWeight: isActive ? 600 : 400,
      }}
      onMouseEnter={e => {
        if (!isActive && !isDisabled) {
          e.currentTarget.style.background = 'var(--bg-hover)'
          e.currentTarget.style.borderColor = 'var(--accent)'
        }
      }}
      onMouseLeave={e => {
        if (!isActive && !isDisabled) {
          e.currentTarget.style.background = 'var(--bg-surface)'
          e.currentTarget.style.borderColor = 'var(--border)'
        }
      }}
    >
      {content}
    </button>
  )

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        flexWrap: 'wrap',
        ...style,
      }}
    >
      {showTotal && (totalItems !== undefined || pageSize !== undefined) && (
        <span style={{ fontSize: sizeStyle.fontSize, color: 'var(--text-muted)', marginRight: 8 }}>
          共 {totalItems ?? (pageSize ? pageSize * total : total)} 条 · {total} 页
        </span>
      )}

      {renderButton('prev', '上一页', () => onChange(current - 1), false, !canPrev)}

      {pages.map((p, i) => {
        if (p === 'ellipsis') {
          return (
            <span
              key={`e-${i}`}
              style={{
                ...sizeStyle,
                color: 'var(--text-muted)',
                display: 'inline-flex',
                alignItems: 'center',
              }}
            >
              ···
            </span>
          )
        }
        return renderButton(`p-${p}`, String(p), () => onChange(p), p === current)
      })}

      {renderButton('next', '下一页', () => onChange(current + 1), false, !canNext)}

      {showQuickJumper && (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginLeft: 8, fontSize: sizeStyle.fontSize, color: 'var(--text-muted)' }}>
          跳至
          <input
            type="number"
            min={1}
            max={total}
            defaultValue={current}
            onKeyDown={e => {
              if (e.key === 'Enter') {
                const v = parseInt((e.target as HTMLInputElement).value)
                if (v >= 1 && v <= total) onChange(v)
              }
            }}
            style={{
              ...sizeStyle,
              width: 50,
              textAlign: 'center',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              color: 'var(--text-primary)',
            }}
          />
          页
        </span>
      )}
    </div>
  )
}
