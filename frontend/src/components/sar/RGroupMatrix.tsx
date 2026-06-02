import { useEffect, useState, useMemo } from 'react'
import { Card } from '../ui'
import { EmptyState } from '../ui'
import { Spinner } from '../ui'
import MoleculeDisplay from '../molecule/MoleculeDisplay'
import type { SARCompound } from '../../types'
import type {
  RGroupMatrix as RGroupMatrixData,
  ActivityHeatmapEntry,
  ActivityHeatmapCell,
} from '../../api/client'
import { buildRGroupMatrix, buildActivityHeatmap } from '../../api/client'

// ============================================================================
// Types
// ============================================================================

export interface RGroupMatrixProps {
  /** 化合物列表（带 SMILES + 活性数据） */
  compounds: SARCompound[]
  /** 预定义共同骨架（不传则自动提取） */
  coreSmiles?: string
  /** IC50 默认 "lower is better"，%inhibition 等设 false */
  lowerIsBetter?: boolean
  /** 矩阵行点击回调（用于跳转分子详情） */
  onCompoundClick?: (compound: SARCompound) => void
}

// ============================================================================
// Helpers
// ============================================================================

/** 根据 activity + units 计算 IC50 nM 归一化值，用于热力图颜色映射。 */
function activityToNM(activity: number | undefined, units: string | undefined): number | null {
  if (activity == null) return null
  if (units === 'uM' || units === 'μM') return activity * 1000
  if (units === 'mM') return activity * 1e6
  if (units === 'nM' || !units) return activity
  return activity
}

/** 取 -log10(IC50 in M) 作颜色映射，范围 0-12 覆盖 uM→pM。 */
function pActScale(activity: number | undefined, units: string | undefined): number | null {
  const nM = activityToNM(activity, units)
  if (nM == null || nM <= 0) return null
  // pIC50 = -log10(M) = -log10(nM * 1e-9) = 9 - log10(nM)
  return 9 - Math.log10(nM)
}

/** 颜色：从红（低 pIC50 = 弱）→ 黄 → 绿（高 pIC50 = 强）。 */
function activityColor(pAct: number | null): string {
  if (pAct == null) return 'transparent'
  // clamp 0-12
  const p = Math.max(0, Math.min(12, pAct))
  const t = p / 12
  // 红(220, 38, 38) → 黄(250, 204, 21) → 绿(34, 197, 94)
  const r = Math.round(220 + t * (34 - 220) * Math.min(1, t * 2))
  const g = Math.round(38 + t * (197 - 38))
  const b = Math.round(38 + t * (94 - 38) * Math.min(1, (1 - t) * 2))
  return `rgb(${r}, ${g}, ${b})`
}

/** 截断 SMILES 展示。 */
function shortSmiles(s: string, max = 18): string {
  if (!s || s === '—') return s || '—'
  return s.length > max ? `${s.slice(0, max - 1)}…` : s
}

/** 格式化活性数值。 */
function formatActivity(value: number | undefined, units: string | undefined): string {
  if (value == null) return '—'
  const formatted = value < 0.01 ? value.toFixed(3) : value.toFixed(2)
  return `${formatted} ${units ?? ''}`
}

// ============================================================================
// Main component
// ============================================================================

/**
 * R-Group 矩阵视图。
 *
 * 功能：
 * - 自动从化合物列表提取共同骨架（后端 MCS 算法）
 * - 表格：行=化合物，列=R-group 位置，单元格=取代基 SMILES
 * - 右侧活性热力图：按 R 位置 × 取代基聚合活性，颜色编码
 *
 * 数据流：
 * 1. POST /api/v1/sar/matrix    → 共同骨架 + 矩阵数据
 * 2. POST /api/v1/sar/heatmap   → 聚合热力图
 */
export default function RGroupMatrixView({
  compounds,
  coreSmiles,
  lowerIsBetter = true,
  onCompoundClick,
}: RGroupMatrixProps) {
  const [matrix, setMatrix] = useState<RGroupMatrixData | null>(null)
  const [heatmaps, setHeatmaps] = useState<ActivityHeatmapEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showHeatmap, setShowHeatmap] = useState(true)

  // 后端 matrix 调用
  useEffect(() => {
    if (!compounds || compounds.length < 2) {
      setMatrix(null)
      setHeatmaps([])
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    buildRGroupMatrix(
      compounds.map(c => ({
        id: c.id,
        name: c.name,
        smiles: c.smiles,
        activity: c.activity ?? null,
        activity_type: c.activityType ?? null,
        units: c.units ?? null,
      })),
      coreSmiles,
      !coreSmiles,
    )
      .then(resp => {
        if (cancelled) return
        if (!resp.success || !resp.core_smiles) {
          setError(resp.error || '未找到共同骨架')
          setMatrix(null)
          return
        }
        setMatrix({
          core_smiles: resp.core_smiles,
          r_labels: resp.r_labels ?? [],
          rows: resp.rows ?? [],
          compounds: resp.compounds ?? [],
          unmatched_count: resp.unmatched_count ?? 0,
        })
      })
      .catch(e => {
        if (cancelled) return
        setError(String(e))
        setMatrix(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [compounds, coreSmiles])

  // heatmap 调用
  useEffect(() => {
    if (!matrix) {
      setHeatmaps([])
      return
    }
    let cancelled = false
    buildActivityHeatmap(matrix, lowerIsBetter)
      .then(resp => {
        if (cancelled) return
        if (resp.success) setHeatmaps(resp.heatmaps)
      })
      .catch(() => {
        // 热力图失败不阻塞矩阵展示
      })
    return () => {
      cancelled = true
    }
  }, [matrix, lowerIsBetter])

  // 找出最优/最差 pIC50 用于热力图图例
  const heatmapStats = useMemo(() => {
    const allPActs: number[] = []
    for (const h of heatmaps) {
      for (const cell of h.cells) {
        if (cell.avg_activity > 0) {
          const pAct = 9 - Math.log10(cell.avg_activity)
          if (Number.isFinite(pAct)) allPActs.push(pAct)
        }
      }
    }
    if (allPActs.length === 0) return null
    return {
      min: Math.min(...allPActs),
      max: Math.max(...allPActs),
    }
  }, [heatmaps])

  // ----- Render states -----

  if (loading) {
    return (
      <Card padding="40px" style={{ display: 'flex', justifyContent: 'center' }}>
        <Spinner />
        <span style={{ marginLeft: 12, color: 'var(--text-muted)', fontSize: 13 }}>
          正在提取共同骨架并构建 R-group 矩阵…
        </span>
      </Card>
    )
  }

  if (error) {
    return (
      <EmptyState
        message={`R-Group 分析失败：${error}`}
        error
      />
    )
  }

  if (!matrix) {
    return (
      <EmptyState message="至少需要 2 个化合物才能进行 R-Group 分析" />
    )
  }

  if (matrix.r_labels.length === 0 || matrix.rows.length === 0) {
    return (
      <EmptyState
        message={`未找到跨越所有化合物的共同骨架（${matrix.unmatched_count} 个化合物不匹配）`}
      />
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 共同骨架展示 */}
      <CoreScaffoldCard coreSmiles={matrix.core_smiles} compoundCount={matrix.compounds.length} unmatched={matrix.unmatched_count} />

      {/* 工具栏：切换热力图 */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button
          onClick={() => setShowHeatmap(v => !v)}
          style={{
            padding: '6px 12px',
            fontSize: 12,
            background: 'var(--bg-surface)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            cursor: 'pointer',
          }}
        >
          {showHeatmap ? '隐藏' : '显示'} 活性热力图
        </button>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          IC50 数据：数值越低活性越高（{lowerIsBetter ? 'lower is better' : 'higher is better'}）
        </span>
      </div>

      {/* 矩阵表格 + 热力图 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: showHeatmap ? 'minmax(0, 1.4fr) minmax(0, 1fr)' : '1fr',
          gap: 16,
          alignItems: 'start',
        }}
      >
        <MatrixTable
          matrix={matrix}
          onCompoundClick={onCompoundClick}
        />
        {showHeatmap && (
          <HeatmapPanel
            heatmaps={heatmaps}
            stats={heatmapStats}
            lowerIsBetter={lowerIsBetter}
          />
        )}
      </div>
    </div>
  )
}

// ============================================================================
// Sub-components
// ============================================================================

function CoreScaffoldCard({
  coreSmiles,
  compoundCount,
  unmatched,
}: {
  coreSmiles: string
  compoundCount: number
  unmatched: number
}) {
  return (
    <Card padding={20}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>核心骨架（Core Scaffold）</h3>
          <p style={{ margin: '4px 0 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
            所有化合物共享的结构（MCS 自动提取）
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {unmatched > 0 && (
            <span
              style={{
                fontSize: 11,
                padding: '2px 8px',
                background: 'var(--warning-muted, #fef3c7)',
                color: 'var(--warning, #b45309)',
                borderRadius: 4,
              }}
            >
              {unmatched} 个未匹配
            </span>
          )}
          <span
            style={{
              fontSize: 11,
              padding: '2px 8px',
              background: 'var(--accent-muted)',
              color: 'var(--accent)',
              borderRadius: 4,
              fontWeight: 500,
            }}
          >
            {compoundCount} 个衍生物
          </span>
        </div>
      </div>
      <div
        style={{
          background: 'var(--bg-base)',
          borderRadius: 8,
          padding: 16,
          display: 'flex',
          alignItems: 'center',
          gap: 16,
        }}
      >
        <MoleculeDisplay
          smiles={coreSmiles}
          name="Core Scaffold"
          size={120}
          showMetadata={false}
          mode="view"
          style={{ border: 'none', padding: 0, background: 'transparent' }}
        />
        <code
          style={{
            flex: 1,
            fontFamily: 'monospace',
            fontSize: 12,
            color: 'var(--text-primary)',
            wordBreak: 'break-all',
          }}
        >
          {coreSmiles}
        </code>
      </div>
    </Card>
  )
}

function MatrixTable({
  matrix,
  onCompoundClick,
}: {
  matrix: RGroupMatrixData
  onCompoundClick?: (c: SARCompound) => void
}) {
  return (
    <Card padding={0}>
      <div style={{ overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 12,
          }}
        >
          <thead>
            <tr style={{ background: 'var(--bg-base)' }}>
              <th
                style={{
                  padding: '10px 12px',
                  textAlign: 'left',
                  fontWeight: 600,
                  color: 'var(--text-muted)',
                  borderBottom: '1px solid var(--border)',
                  minWidth: 120,
                }}
              >
                化合物
              </th>
              {matrix.r_labels.map(label => (
                <th
                  key={label}
                  style={{
                    padding: '10px 12px',
                    textAlign: 'center',
                    fontWeight: 600,
                    color: 'var(--accent)',
                    borderBottom: '1px solid var(--border)',
                    minWidth: 100,
                  }}
                >
                  {label}
                </th>
              ))}
              <th
                style={{
                  padding: '10px 12px',
                  textAlign: 'right',
                  fontWeight: 600,
                  color: 'var(--text-muted)',
                  borderBottom: '1px solid var(--border)',
                }}
              >
                活性
              </th>
            </tr>
          </thead>
          <tbody>
            {matrix.compounds.map((c, rowIdx) => {
              const activity = c.activity as number | undefined
              const units = (c.units as string | undefined) ?? ''
              const matches = c.matches
              const pAct = pActScale(activity, units)
              return (
                <tr
                  key={c.id || rowIdx}
                  onClick={() => {
                    if (matches && onCompoundClick) {
                      onCompoundClick({
                        id: c.id,
                        smiles: c.smiles,
                        name: c.name,
                        rGroups: {},
                        activity,
                        activityType: c.activity_type as string | undefined,
                        units,
                      })
                    }
                  }}
                  style={{
                    cursor: matches && onCompoundClick ? 'pointer' : 'default',
                    borderBottom: '1px solid var(--border)',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => {
                    if (matches && onCompoundClick) {
                      e.currentTarget.style.background = 'var(--bg-elevated)'
                    }
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = 'transparent'
                  }}
                >
                  <td style={{ padding: '8px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
                        {c.name}
                      </span>
                      {!matches && (
                        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>未匹配</span>
                      )}
                    </div>
                  </td>
                  {matrix.r_labels.map((label, colIdx) => {
                    const sub = matrix.rows[rowIdx]?.[colIdx] ?? '—'
                    return (
                      <td
                        key={label}
                        style={{
                          padding: '8px 12px',
                          textAlign: 'center',
                          fontFamily: 'monospace',
                          fontSize: 11,
                          color: sub === '—' ? 'var(--text-muted)' : 'var(--text-primary)',
                        }}
                        title={sub}
                      >
                        {shortSmiles(sub)}
                      </td>
                    )
                  })}
                  <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '2px 8px',
                        borderRadius: 4,
                        background: activityColor(pAct),
                        color: pAct != null && pAct > 6 ? 'white' : 'var(--text-primary)',
                        fontFamily: 'monospace',
                        fontSize: 11,
                        fontWeight: 500,
                      }}
                    >
                      {formatActivity(activity, units)}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function HeatmapPanel({
  heatmaps,
  stats,
  lowerIsBetter,
}: {
  heatmaps: ActivityHeatmapEntry[]
  stats: { min: number; max: number } | null
  lowerIsBetter: boolean
}) {
  if (heatmaps.length === 0) {
    return (
      <Card padding={20}>
        <EmptyState message="无活性数据" />
      </Card>
    )
  }

  return (
    <Card padding={20}>
      <h3 style={{ margin: '0 0 4px 0', fontSize: 14, fontWeight: 600 }}>活性热力图</h3>
      <p style={{ margin: '0 0 16px 0', fontSize: 11, color: 'var(--text-muted)' }}>
        按 R 位置 × 取代基聚合均值活性（pIC50 颜色编码，{lowerIsBetter ? '数值越低越好' : '数值越高越好'}）
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {heatmaps.map(h => (
          <HeatmapRow key={h.r_label} entry={h} />
        ))}
      </div>

      {stats && <ColorLegend min={stats.min} max={stats.max} lowerIsBetter={lowerIsBetter} />}
    </Card>
  )
}

function HeatmapRow({ entry }: { entry: ActivityHeatmapEntry }) {
  if (entry.cells.length === 0) {
    return (
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--accent)' }}>
          {entry.r_label}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>无数据</div>
      </div>
    )
  }

  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--accent)' }}>
        {entry.r_label} <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>({entry.cells.length} 种取代基)</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {entry.cells.map((cell, idx) => (
          <HeatmapCellRow
            key={`${cell.substituent_smiles}-${idx}`}
            cell={cell}
            rank={idx + 1}
            best={idx === 0}
          />
        ))}
      </div>
    </div>
  )
}

function HeatmapCellRow({
  cell,
  rank,
  best,
}: {
  cell: ActivityHeatmapCell
  rank: number
  best: boolean
}) {
  const pAct = 9 - Math.log10(cell.avg_activity)
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 10px',
        background: activityColor(pAct),
        borderRadius: 4,
        fontSize: 11,
        color: pAct > 6 ? 'white' : 'var(--text-primary)',
        transition: 'transform 0.1s',
      }}
    >
      <span style={{ fontWeight: 600, minWidth: 20 }}>#{rank}</span>
      <code style={{ flex: 1, fontFamily: 'monospace', fontSize: 11 }} title={cell.substituent_smiles}>
        {shortSmiles(cell.substituent_smiles, 24)}
      </code>
      <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>
        {cell.avg_activity < 0.01 ? cell.avg_activity.toFixed(3) : cell.avg_activity.toFixed(2)}
      </span>
      {best && <span style={{ fontSize: 10, fontWeight: 600 }}>★</span>}
      {cell.count > 1 && (
        <span style={{ fontSize: 10, opacity: 0.8 }}>n={cell.count}</span>
      )}
    </div>
  )
}

function ColorLegend({
  min,
  max,
  lowerIsBetter,
}: {
  min: number
  max: number
  lowerIsBetter: boolean
}) {
  // 渐变条
  const steps = 10
  return (
    <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>
        pIC50 颜色图例（{lowerIsBetter ? '绿=高活性' : '绿=低活性'}）
      </div>
      <div
        style={{
          display: 'flex',
          height: 8,
          borderRadius: 4,
          overflow: 'hidden',
        }}
      >
        {Array.from({ length: steps }).map((_, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              background: activityColor(min + ((max - min) * i) / (steps - 1)),
            }}
          />
        ))}
      </div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 10,
          color: 'var(--text-muted)',
          marginTop: 4,
        }}
      >
        <span>pIC50 {min.toFixed(1)}</span>
        <span>pIC50 {max.toFixed(1)}</span>
      </div>
    </div>
  )
}
