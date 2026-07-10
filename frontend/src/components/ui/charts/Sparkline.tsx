import { useMemo } from 'react'

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

    let linePath: string
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
