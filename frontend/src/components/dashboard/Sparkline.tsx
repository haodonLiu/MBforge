import { useMemo } from 'react'

// ============================================================================
// 简易折线图（SVG 自绘）
// ============================================================================

export interface SparklineProps {
  data: number[]
  width?: number | string
  height?: number
  color?: string
  fillColor?: string
  strokeWidth?: number
  showDots?: boolean
  showGrid?: boolean
  /** 是否平滑曲线（默认 true）*/
  smooth?: boolean
}

export default function Sparkline({
  data,
  width = 240,
  height = 60,
  color = 'var(--accent)',
  fillColor,
  strokeWidth = 2,
  showDots = false,
  showGrid = false,
  smooth = true,
}: SparklineProps) {
  const numWidth = typeof width === 'number' ? width : 240
  const { path, fillPath, points } = useMemo(() => {
    if (data.length === 0) return { path: '', fillPath: '', points: [] }

    const max = Math.max(...data)
    const min = Math.min(...data)
    const range = max - min || 1
    const padding = 4

    const w = numWidth - padding * 2
    const h = height - padding * 2
    const stepX = data.length > 1 ? w / (data.length - 1) : 0

    const pts = data.map((v, i) => ({
      x: padding + i * stepX,
      y: padding + h - ((v - min) / range) * h,
    }))

    let linePath = ''
    if (smooth && pts.length > 1) {
      // 平滑曲线（贝塞尔）
      linePath = `M ${pts[0].x} ${pts[0].y}`
      for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[i]
        const p1 = pts[i + 1]
        const cx = (p0.x + p1.x) / 2
        linePath += ` C ${cx} ${p0.y}, ${cx} ${p1.y}, ${p1.x} ${p1.y}`
      }
    } else {
      linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
    }

    // 填充区域（在曲线下方）
    const areaPath = `${linePath} L ${pts[pts.length - 1].x} ${height - padding} L ${pts[0].x} ${height - padding} Z`

    return { path: linePath, fillPath: areaPath, points: pts }
  }, [data, width, height, smooth])

  return (
    <svg width={numWidth} height={height} style={{ display: 'block', maxWidth: '100%' }}>
      {showGrid && (
        <g>
          {[0.25, 0.5, 0.75].map(t => (
            <line
              key={t}
              x1={0}
              y1={height * t}
              x2={numWidth}
              y2={height * t}
              stroke="var(--bg-elevated)"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
          ))}
        </g>
      )}
      {fillColor && (
        <path
          d={fillPath}
          fill={fillColor}
          opacity={0.2}
        />
      )}
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showDots && points.map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={3}
          fill={color}
        />
      ))}
    </svg>
  )
}

// ============================================================================
// 柱状图
// ============================================================================

export interface BarChartProps {
  data: Array<{ label: string; value: number; color?: string }>
  width?: number | string
  height?: number
  showValues?: boolean
  barColor?: string
  highlightLast?: boolean
}

export function BarChart({
  data,
  width = 240,
  height = 120,
  showValues = true,
  barColor = 'var(--accent)',
  highlightLast = false,
}: BarChartProps) {
  if (data.length === 0) return null

  const max = Math.max(...data.map(d => d.value))
  const numWidth = typeof width === 'number' ? width : 240
  const padding = 24
  const w = numWidth - padding * 2
  const h = height - padding * 2
  const barWidth = (w / data.length) * 0.7
  const gap = (w / data.length) * 0.3

  return (
    <svg width={numWidth} height={height} style={{ display: 'block', maxWidth: '100%' }}>
      {/* Y 轴基线 */}
      <line
        x1={padding}
        y1={padding + h}
        x2={padding + w}
        y2={padding + h}
        stroke="var(--bg-elevated)"
        strokeWidth={1}
      />
      {data.map((d, i) => {
        const barH = max > 0 ? (d.value / max) * h : 0
        const x = padding + i * (barWidth + gap) + gap / 2
        const y = padding + h - barH
        const isLast = i === data.length - 1
        const fill = d.color ?? (isLast && highlightLast ? 'var(--success)' : barColor)
        return (
          <g key={i}>
            <rect
              x={x}
              y={y}
              width={barWidth}
              height={barH}
              fill={fill}
              opacity={isLast && highlightLast ? 1 : 0.85}
              rx={3}
            />
            {showValues && (
              <text
                x={x + barWidth / 2}
                y={y - 4}
                textAnchor="middle"
                fontSize={10}
                fill="var(--text-muted)"
              >
                {d.value}
              </text>
            )}
            <text
              x={x + barWidth / 2}
              y={padding + h + 14}
              textAnchor="middle"
              fontSize={10}
              fill="var(--text-muted)"
            >
              {d.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

// ============================================================================
// 圆环图（占比）
// ============================================================================

export interface DonutChartProps {
  data: Array<{ label: string; value: number; color: string }>
  size?: number
  thickness?: number
  showLegend?: boolean
}

export function DonutChart({
  data,
  size = 160,
  thickness = 20,
  showLegend = true,
}: DonutChartProps) {
  const total = data.reduce((s, d) => s + d.value, 0)
  const radius = (size - thickness) / 2
  const circumference = 2 * Math.PI * radius
  const center = size / 2

  let offset = 0

  if (total === 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <div style={{
          width: size, height: size, borderRadius: '50%',
          border: `${thickness}px solid var(--bg-elevated)`,
        }} />
        {showLegend && <span style={{ color: 'var(--text-muted)' }}>暂无数据</span>}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', flexShrink: 0 }}>
        {data.map((d, i) => {
          const len = (d.value / total) * circumference
          const dashArray = `${len} ${circumference - len}`
          const segment = (
            <circle
              key={i}
              cx={center}
              cy={center}
              r={radius}
              fill="none"
              stroke={d.color}
              strokeWidth={thickness}
              strokeDasharray={dashArray}
              strokeDashoffset={-offset}
            />
          )
          offset += len
          return segment
        })}
      </svg>
      {showLegend && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {data.map((d, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
              <span style={{
                width: 10, height: 10, borderRadius: 2,
                background: d.color, flexShrink: 0,
              }} />
              <span style={{ color: 'var(--text-secondary)' }}>{d.label}</span>
              <span style={{ color: 'var(--text-primary)', fontWeight: 600, marginLeft: 'auto' }}>
                {d.value}
              </span>
              <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                {Math.round((d.value / total) * 100)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// 热力图（每日活动）
// ============================================================================

export interface HeatmapProps {
  /** 数据点：每个元素的 value 决定颜色深浅 */
  data: Array<{ date: string; value: number }>
  /** 显示最近多少天（默认 84 = 12 周）*/
  days?: number
}

export function Heatmap({ data, days = 84 }: HeatmapProps) {
  // 取最近 N 天
  const recent = useMemo(() => {
    return data.slice(-days)
  }, [data, days])

  const max = Math.max(...recent.map(d => d.value), 1)
  const weeks: Array<Array<typeof recent[0]>> = []
  for (let i = 0; i < recent.length; i += 7) {
    weeks.push(recent.slice(i, i + 7))
  }

  const colorByLevel = (level: number) => {
    if (level === 0) return 'var(--bg-elevated)'
    if (level < 0.25) return 'rgba(99,102,241,0.3)'
    if (level < 0.5) return 'rgba(99,102,241,0.5)'
    if (level < 0.75) return 'rgba(99,102,241,0.7)'
    return 'var(--accent)'
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
        {weeks.map((week, wi) => (
          <div key={wi} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {week.map((d, di) => (
              <div
                key={di}
                title={`${d.date}: ${d.value}`}
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: 2,
                  background: colorByLevel(d.value / max),
                }}
              />
            ))}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'var(--text-muted)' }}>
        <span>少</span>
        {[0, 0.25, 0.5, 0.75, 1].map((l, i) => (
          <div
            key={i}
            style={{
              width: 12, height: 12, borderRadius: 2,
              background: colorByLevel(l),
            }}
          />
        ))}
        <span>多</span>
      </div>
    </div>
  )
}
