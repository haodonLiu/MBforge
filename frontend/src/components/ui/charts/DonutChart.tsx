import { useMemo } from 'react'

export interface DonutChartProps {
  data: Array<{ label: string; value: number; color: string }>
  size?: number
  thickness?: number
  showLegend?: boolean
}

export default function DonutChart({
  data,
  size = 160,
  thickness = 20,
  showLegend = true,
}: DonutChartProps) {
  const total = data.reduce((s, d) => s + d.value, 0)
  const radius = (size - thickness) / 2
  const circumference = 2 * Math.PI * radius
  const center = size / 2

  const segments = useMemo(() => {
    return data.map((d, i) => {
      const len = (d.value / total) * circumference
      const dashArray = `${len} ${circumference - len}`
      const dashOffset = -data.slice(0, i).reduce((s, prev) => s + (prev.value / total) * circumference, 0)
      return { len, dashArray, dashOffset }
    })
  }, [data, total, circumference])

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
          const { dashArray, dashOffset } = segments[i]
          return (
            <circle
              key={i}
              cx={center}
              cy={center}
              r={radius}
              fill="none"
              stroke={d.color}
              strokeWidth={thickness}
              strokeDasharray={dashArray}
              strokeDashoffset={dashOffset}
            />
          )
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
