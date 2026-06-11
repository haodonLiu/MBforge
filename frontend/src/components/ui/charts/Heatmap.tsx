import { useMemo } from 'react'

export interface HeatmapProps {
  /** 数据点：每个元素的 value 决定颜色深浅 */
  data: Array<{ date: string; value: number }>
  /** 显示最近多少天（默认 84 = 12 周）*/
  days?: number
}

export default function Heatmap({ data, days = 84 }: HeatmapProps) {
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
    if (level < 0.25) return 'var(--accent-muted)'
    if (level < 0.5) return 'color-mix(in srgb, var(--accent) 50%, var(--bg-elevated))'
    if (level < 0.75) return 'color-mix(in srgb, var(--accent) 75%, var(--bg-elevated))'
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
