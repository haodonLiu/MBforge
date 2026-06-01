import type { ReactNode } from 'react'
import { hstack } from '../../styles/patterns'

export interface SettingSectionProps {
  title?: string
  description?: string
  children?: ReactNode
  /** 主轴方向：horizontal（label 左，control 右） / stacked（label 上，control 下） */
  layout?: 'horizontal' | 'stacked'
  style?: React.CSSProperties
}

/** 设置项容器：标题 + 描述 + 子控件 */
export function SettingItem({ title, description, children, layout = 'horizontal', style }: SettingSectionProps) {
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
        <div className="setting-info" style={{ flex: layout === 'horizontal' ? 1 : undefined, minWidth: 0 }}>
          {title && <div className="setting-label" style={{ fontSize: '13px', fontWeight: 500 }}>{title}</div>}
          {description && (
            <div className="setting-desc" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              {description}
            </div>
          )}
        </div>
      )}
      <div style={{ flexShrink: 0 }}>{children}</div>
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
