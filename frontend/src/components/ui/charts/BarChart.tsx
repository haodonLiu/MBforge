export interface BarChartProps {
  data: Array<{ label: string; value: number; color?: string }>
  width?: number | string
  height?: number
  showValues?: boolean
  barColor?: string
  highlightLast?: boolean
}

export default function BarChart({
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
