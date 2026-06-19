import { useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'

export interface TabItem {
  /** 唯一标识 */
  key: string
  /** 标签文本 */
  label: ReactNode
  /** 是否禁用 */
  disabled?: boolean
  /** 角标（如未读数）*/
  badge?: string | number
}

export interface TabsProps {
  items: TabItem[]
  /** 当前激活的 tab key */
  activeKey?: string
  /** 默认激活的 tab key（非受控）*/
  defaultActiveKey?: string
  /** tab 切换回调 */
  onChange?: (key: string) => void
  /** 标签位置（预留字段，未来支持 bottom 布局）*/
  position?: 'top' | 'bottom'
  /** 变体 */
  variant?: 'default' | 'pills' | 'underline' | 'segment'
  size?: 'sm' | 'md' | 'lg'
  /** 是否填满整行 */
  fullWidth?: boolean
  style?: React.CSSProperties
  className?: string
}

const sizeMap = {
  sm: { padding: '6px 12px', fontSize: '12px' },
  md: { padding: '8px 16px', fontSize: '13px' },
  lg: { padding: '10px 20px', fontSize: '14px' },
}

/**
 * Tabs 标签页组件。
 *
 * 支持受控/非受控两种模式，3 种视觉变体，键盘可访问。
 */
export default function Tabs({
  items,
  activeKey,
  defaultActiveKey,
  onChange,
   
  position: _position = 'top',
  variant = 'default',
  size = 'md',
  fullWidth = false,
  style,
  className,
}: TabsProps) {
  const [internalKey, setInternalKey] = useState(defaultActiveKey ?? items[0]?.key)
  const isControlled = activeKey !== undefined
  const currentKey = isControlled ? activeKey : internalKey

  const handleClick = (key: string, disabled?: boolean) => {
    if (disabled) return
    if (!isControlled) setInternalKey(key)
    onChange?.(key)
  }

  const renderTab = (item: TabItem) => {
    const isActive = item.key === currentKey
    const sizeStyle = sizeMap[size]

    const baseStyle: React.CSSProperties = {
      ...sizeStyle,
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      border: 'none',
      background: 'transparent',
      color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
      cursor: item.disabled ? 'not-allowed' : 'pointer',
      opacity: item.disabled ? 0.4 : 1,
      fontWeight: isActive ? 600 : 500,
      transition: 'all 0.15s',
      flex: fullWidth ? 1 : undefined,
      justifyContent: fullWidth ? 'center' : undefined,
      position: 'relative',
    }

    if (variant === 'pills') {
      return (
        <button
          key={item.key}
          type="button"
          role="tab"
          aria-selected={isActive}
          onClick={() => handleClick(item.key, item.disabled)}
          disabled={item.disabled}
          className={className}
          style={{
            ...baseStyle,
            background: isActive ? 'var(--accent-muted)' : 'transparent',
            borderRadius: 8,
          }}
        >
          {item.label}
          {item.badge !== undefined && (
            <span style={{
              padding: '1px 6px',
              background: 'var(--accent)',
              color: 'white',
              borderRadius: 8,
              fontSize: 10,
              fontWeight: 600,
            }}>
              {item.badge}
            </span>
          )}
        </button>
      )
    }

    if (variant === 'segment') {
      return (
        <button
          key={item.key}
          type="button"
          role="tab"
          aria-selected={isActive}
          onClick={() => handleClick(item.key, item.disabled)}
          disabled={item.disabled}
          className={className}
          style={{
            ...baseStyle,
            background: isActive ? 'var(--bg-elevated)' : 'transparent',
            borderRadius: 'var(--radius-md)',
            boxShadow: isActive ? 'var(--shadow-card)' : 'none',
          }}
        >
          {item.label}
          {item.badge !== undefined && (
            <span style={{
              padding: '1px 6px',
              background: 'var(--bg-elevated)',
              color: 'var(--text-muted)',
              borderRadius: 8,
              fontSize: 10,
              fontWeight: 600,
            }}>
              {item.badge}
            </span>
          )}
        </button>
      )
    }

    return (
      <button
        key={item.key}
        type="button"
        role="tab"
        aria-selected={isActive}
        onClick={() => handleClick(item.key, item.disabled)}
        disabled={item.disabled}
        className={className}
        style={baseStyle}
      >
        {item.label}
        {item.badge !== undefined && (
          <span style={{
            padding: '1px 6px',
            background: 'var(--bg-elevated)',
            color: 'var(--text-muted)',
            borderRadius: 8,
            fontSize: 10,
            fontWeight: 600,
          }}>
            {item.badge}
          </span>
        )}
        {variant === 'underline' && isActive && (
          <motion.div
            layoutId="tabs-underline"
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              bottom: -1,
              height: 2,
              background: 'var(--accent)',
              borderRadius: 1,
            }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          />
        )}
      </button>
    )
  }

  const tabList = (
    <div
      role="tablist"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: variant === 'segment' ? 4 : variant === 'default' ? 4 : 6,
        padding: variant === 'segment' ? 4 : undefined,
        background: variant === 'segment' ? 'var(--bg-surface)' : undefined,
        borderRadius: variant === 'segment' ? 'var(--radius-lg)' : undefined,
        border: variant === 'segment' ? '1px solid var(--border)' : undefined,
        borderBottom: variant === 'default' ? '1px solid var(--border)' : variant === 'segment' ? 'none' : 'none',
        ...(variant === 'underline' && { borderBottom: '1px solid var(--border)' }),
        ...style,
      }}
    >
      {items.map(renderTab)}
    </div>
  )

  return tabList
}

// ============================================================================
// TabPanel - 内容容器（使用 TabsContext 或 activeKey 显式指定）
// ============================================================================

export interface TabPanelProps {
  activeKey: string
  tabKey: string
  children: ReactNode
  /** 强制挂载（保留 DOM）*/
  forceMount?: boolean
}

export function TabPanel({ activeKey, tabKey, children, forceMount = false }: TabPanelProps) {
  if (activeKey !== tabKey && !forceMount) return null
  return (
    <div role="tabpanel" style={{ padding: '16px 0' }}>
      {children}
    </div>
  )
}
