/**
 * CorefBboxOverlay — 在 PDF 页面上叠加渲染 coref 标注
 *
 * 决策 (coref 增强):
 * - 6C: 复用 figure_labels + coref_predictions 数据
 * - 10B: 阈值用户可拖动调节
 * - 11A: 一对多允许（mol 配多个 label 用同色）
 * - 12A: source=geometric 蓝色，source=manual 绿色（未来 source=llm 紫色）
 *
 * 最小可用版本：仅渲染 + 统计。不含右键菜单/拖动条（下次迭代）。
 */

import { useMemo } from 'react'
import type { CSSProperties } from 'react'
import type { FigureLabel, CorefPrediction } from '../../api/tauri/result_pane'

export interface CorefBboxOverlayProps {
  /** OCR 检出的 label 标注（confidence 可用于过滤） */
  labels: FigureLabel[]
  /** 分子 ↔ label 配对预测（按 source 染色） */
  predictions: CorefPrediction[]
  /** 置信度阈值（0-1，低于此值的 prediction 不显示） */
  threshold: number
  /** 父容器尺寸（用于坐标换算，px） */
  containerWidth: number
  containerHeight: number
  /** 点击 mol bbox 回调（用于"重选 coref"菜单） */
  onMolClick?: (molInfo: MolClickInfo) => void
  /** 点击 label bbox 回调 */
  onLabelClick?: (label: FigureLabel) => void
}

export interface MolClickInfo {
  prediction: CorefPrediction
  /** 共享同 source+label 的所有配对（同色组） */
  pairedLabels: FigureLabel[]
}

const SOURCE_COLORS: Record<string, string> = {
  geometric: '#3b82f6', // blue
  manual: '#10b981', // green
  llm: '#a855f7', // purple (预留)
}

const LABEL_DEFAULT_COLOR = '#f59e0b' // amber（未配对的独立 label）

export function CorefBboxOverlay(props: CorefBboxOverlayProps): JSX.Element | null {
  const { labels, predictions, threshold, containerWidth, containerHeight, onMolClick, onLabelClick } = props

  // 过滤低于阈值的 prediction
  const visiblePreds = useMemo(
    () => predictions.filter(p => p.confidence >= threshold),
    [predictions, threshold],
  )

  // mol → color（按 source 分组，同 source 同色）
  const predColor = (p: CorefPrediction): string =>
    SOURCE_COLORS[p.source] ?? LABEL_DEFAULT_COLOR

  // 为每个 prediction 找对应的 label（按 label_id 匹配）
  const labelById = useMemo(() => {
    const m = new Map<number, FigureLabel>()
    for (const l of labels) m.set(l.id, l)
    return m
  }, [labels])

  if (containerWidth <= 0 || containerHeight <= 0) return null

  return (
    <div
      className="coref-bbox-overlay"
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: containerWidth,
        height: containerHeight,
        pointerEvents: 'none',
      }}
    >
      <svg
        width={containerWidth}
        height={containerHeight}
        style={{ position: 'absolute', top: 0, left: 0 }}
      >
        {/* 配对连线（mol ↔ label） */}
        {visiblePreds.map(p => {
          if (!p.mol_bbox || !p.label_bbox) return null
          const [mx1, my1, mx2, my2] = p.mol_bbox
          const [lx1, ly1, lx2, ly2] = p.label_bbox
          const mcx = (mx1 + mx2) / 2 * containerWidth
          const mcy = (my1 + my2) / 2 * containerHeight
          const lcx = (lx1 + lx2) / 2 * containerWidth
          const lcy = (ly1 + ly2) / 2 * containerHeight
          return (
            <line
              key={`conn-${p.id}`}
              x1={mcx}
              y1={mcy}
              x2={lcx}
              y2={lcy}
              stroke={predColor(p)}
              strokeWidth={1.5}
              strokeDasharray="4 2"
              opacity={0.7}
            />
          )
        })}

        {/* Label 框 */}
        {labels.map(l => {
          const [x1, y1, x2, y2] = l.label_bbox
          const visible = visiblePreds.some(
            p => p.label_id === l.id && p.confidence >= threshold,
          )
          if (!visible && threshold > 0) return null
          const color = LABEL_DEFAULT_COLOR
          return (
            <rect
              key={`label-${l.id}`}
              x={x1 * containerWidth}
              y={y1 * containerHeight}
              width={(x2 - x1) * containerWidth}
              height={(y2 - y1) * containerHeight}
              fill="none"
              stroke={color}
              strokeWidth={1.5}
              opacity={0.8}
              style={{ pointerEvents: 'auto', cursor: onLabelClick ? 'pointer' : 'default' }}
              onClick={() => onLabelClick?.(l)}
            >
              <title>
                {l.label_text} (conf={l.ocr_conf.toFixed(2)})
              </title>
            </rect>
          )
        })}

        {/* Mol 框（用 prediction 的 mol_bbox） */}
        {visiblePreds.map(p => {
          if (!p.mol_bbox) return null
          const [x1, y1, x2, y2] = p.mol_bbox
          const color = predColor(p)
          const pairedLabels = visiblePreds
            .filter(q => q.mol_smiles === p.mol_smiles)
            .map(q => q.label_id)
            .filter((id): id is number => id !== null)
            .map(id => labelById.get(id))
            .filter((l): l is FigureLabel => l !== undefined)
          const clickInfo: MolClickInfo = { prediction: p, pairedLabels }
          return (
            <rect
              key={`mol-${p.id}`}
              x={x1 * containerWidth}
              y={y1 * containerHeight}
              width={(x2 - x1) * containerWidth}
              height={(y2 - y1) * containerHeight}
              fill={color}
              fillOpacity={0.1}
              stroke={color}
              strokeWidth={2}
              style={{ pointerEvents: 'auto', cursor: onMolClick ? 'pointer' : 'default' }}
              onClick={() => onMolClick?.(clickInfo)}
            >
              <title>
                {p.mol_smiles ?? '(no SMILES)'} [conf={p.confidence.toFixed(2)}]
              </title>
            </rect>
          )
        })}
      </svg>

      {/* 统计信息（顶部小条） */}
      <div
        style={statsBarStyle}
        title={`显示 ${visiblePreds.length} / 共有 ${predictions.length}`}
      >
        <span>显示 {visiblePreds.length} / 共有 {predictions.length}</span>
        {visiblePreds.length > 0 && (
          <span style={{ marginLeft: 8, fontSize: 11, opacity: 0.7 }}>
            (阈值 {threshold.toFixed(2)})
          </span>
        )}
      </div>
    </div>
  )
}

const statsBarStyle: CSSProperties = {
  position: 'absolute',
  top: 4,
  right: 4,
  background: 'rgba(0, 0, 0, 0.65)',
  color: 'white',
  padding: '2px 8px',
  borderRadius: 4,
  fontSize: 12,
  pointerEvents: 'auto',
  zIndex: 10,
}
