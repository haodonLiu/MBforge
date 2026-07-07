export interface StatCardProps {
  label: string
  value: string | number
  subValue?: string
  variant?: 'default' | 'success' | 'danger'
}

const BG_COLORS: Record<NonNullable<StatCardProps['variant']>, string> = {
  default: 'var(--bg-surface)',
  success: 'rgba(22, 163, 74, 0.08)',
  danger: 'rgba(220, 38, 38, 0.08)',
}

const TEXT_COLORS: Record<NonNullable<StatCardProps['variant']>, string> = {
  default: 'var(--text-primary)',
  success: 'var(--success)',
  danger: 'var(--danger)',
}

/**
 * 顶部统计卡片 — 用于仪表盘关键指标 (模型数 / 缓存大小 / 错误数等).
 * `variant` 控制强调色 (success/danger).
 */
export default function StatCard({
  label,
  value,
  subValue,
  variant = 'default',
}: StatCardProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
        padding: '16px',
        background: BG_COLORS[variant],
        borderRadius: '10px',
        border: '1px solid var(--border)',
      }}
    >
      <div
        style={{
          fontSize: '11px',
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: '20px',
          fontWeight: 700,
          color: TEXT_COLORS[variant],
        }}
      >
        {value}
      </div>
      {subValue && (
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{subValue}</div>
      )}
    </div>
  )
}
