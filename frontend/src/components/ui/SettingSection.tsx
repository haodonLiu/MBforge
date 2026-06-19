import type { ReactNode } from 'react'
import { hstack } from '../../styles/patterns'

export interface SettingItemProps {
  title?: string
  description?: string
  children?: ReactNode
  /** 主轴方向：horizontal（label 左，control 右） / stacked（label 上，control 下） */
  layout?: 'horizontal' | 'stacked'
  /** label/info 区域在 horizontal 布局下的固定宽度（默认 160px） */
  labelWidth?: number
  /** 是否显示“已修改”脏标记小圆点 */
  dirty?: boolean
  style?: React.CSSProperties
}

/** 历史兼容别名，仍被部分类型聚合文件引用 */
export type SettingSectionProps = SettingItemProps

/** 设置项容器：标题 + 描述 + 子控件 */
export function SettingItem({
  title,
  description,
  children,
  layout = 'horizontal',
  labelWidth = 160,
  dirty,
  style,
}: SettingItemProps) {
  return (
    <div
      className="setting-item"
      style={{
        ...hstack(layout === 'horizontal' ? 16 : 8),
        flexDirection: layout === 'stacked' ? 'column' : 'row',
        alignItems: layout === 'stacked' ? 'flex-start' : 'center',
        ...style,
      }}
    >
      {(title || description) && (
        <div
          className="setting-info"
          style={{
            width: layout === 'horizontal' ? labelWidth : undefined,
            flexShrink: 0,
            minWidth: 0,
          }}
        >
          {title && <div className="setting-label" style={{ fontSize: '13px', fontWeight: 500 }}>{title}</div>}
          {description && (
            <div className="setting-desc" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              {description}
            </div>
          )}
        </div>
      )}
      <div style={{ flex: 1, minWidth: 280, maxWidth: 480, display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
        {children}
        {dirty && <span className="setting-dirty-dot" aria-label="Modified" />}
      </div>
    </div>
  )
}

/** 设置分组容器：标题 + 多个 SettingItem */
export function SettingGroup({ title, children, style }: { title?: string; children: ReactNode; style?: React.CSSProperties }) {
  return (
    <div className="settings-group" style={style}>
      {title && (
        <h3 className="settings-group-title" style={{
          fontSize: '12px',
          fontWeight: 600,
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          margin: '0 0 12px 0',
        }}>
          {title}
        </h3>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {children}
      </div>
    </div>
  )
}

/** 设置 Section 容器 */
export default function SettingSection({ children, style }: { children: ReactNode; style?: React.CSSProperties }) {
  return (
    <div className="settings-section" style={{ display: 'flex', flexDirection: 'column', gap: 20, ...style }}>
      {children}
    </div>
  )
}
