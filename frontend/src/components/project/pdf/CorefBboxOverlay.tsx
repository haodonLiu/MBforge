/**
 * CorefBboxOverlay — 在 PDF 页面上叠加渲染 coref 标注
 *
 * 决策 (coref 增强):
 * - 6C: 复用 figure_labels + coref_predictions 数据
 * - 10B: 阈值用户可拖动调节
 * - 11A: 一对多允许（mol 配多个 label 用同色）
 * - 12A: source=geometric 蓝色，source=manual 绿色（未来 source=llm 紫色）
 *
 * 坐标投影：
 *   label_bbox / mol_bbox in KB = figure 内归一化 0-1（图像坐标，左上原点）
 *   通过 `figureBoxes: Map<imageBasename, bbox_pdf>` 把它们投影到 PDF 页面坐标
 *   再走与 MoleculeOverlay/OcrOverlay 相同的 `pdfToCss` 渲染路径
 *   （containerWidth/Height = pageInfo.width/height，originalHeight = pageInfo.originalHeight，scale = pageInfo.scale）
 */

import { useMemo } from 'react'
import type { CSSProperties, MouseEvent as ReactMouseEvent } from 'react'
import type { FigureLabel, CorefPrediction } from '../../../api/http/result_pane'
import { pdfToCss } from '../../../utils/pdf'

export interface CorefBboxOverlayProps {
  /** OCR 检出的 label 标注（confidence 可用于过滤） */
  labels: FigureLabel[]
  /** 分子 ↔ label 配对预测（按 source 染色） */
  predictions: CorefPrediction[]
  /** 置信度阈值（0-1，低于此值的 prediction 不显示） */
  threshold: number
  /** PDF 页面渲染宽度（CSS 像素） */
  containerWidth: number
  /** PDF 页面渲染高度（CSS 像素） */
  containerHeight: number
  /** PDF 页面原始高度（PDF points, 72 DPI）— 用于 pdfToCss Y 翻转 */
  originalHeight: number
  /** 缩放比例 — 用于 pdfToCss */
  scale: number
  /** figure 在页面上的 bbox（[x1,y1,x2,y2] in PDF points），key 为 image_path basename */
  figureBoxes: Map<string, [number, number, number, number]>
  /** 点击 mol bbox 回调（用于"重选 coref"菜单） */
  onMolClick?: (molInfo: MolClickInfo) => void
  /** 右键点击 mol bbox 回调（用于打开上下文菜单） */
  onMolContextMenu?: (molInfo: MolClickInfo, e: ReactMouseEvent) => void
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

/** 把 figure 内归一化 0-1 bbox 投影到页面 PDF coords（PDF points）。
 *
 * image_bbox in figure: [x1, y1, x2, y2] ∈ [0,1]²，左上原点
 * figure bbox on page (in props.figureBoxes): [x1, y1, x2, y2] in PDF points, 左下原点
 *
 * 公式：
 *   page_x = fig_x1 + lbl_x * (fig_x2 - fig_x1)
 *   page_y_top_origin = fig_y2 - lbl_y * (fig_y2 - fig_y1)
 *   → 转 PDF 左下原点：
 *     pdf_y1 = page_h_pts - page_y_top_y2  // 等价于 image_to_pdf_bbox 的反向思路
 *     pdf_y2 = page_h_pts - page_y_top_y1
 */
function projectFigureBboxToPage(
  imgBbox: [number, number, number, number],
  figBboxPdf: [number, number, number, number],
): [number, number, number, number] | null {
  const [lx1, ly1, lx2, ly2] = imgBbox
  const [fx1, fy1, fx2, fy2] = figBboxPdf
  const fw = fx2 - fx1
  const fh = fy2 - fy1
  if (fw <= 0 || fh <= 0) return null
  // image y=0 在 figure 顶部 → 对应 page_y_top = fy2（最大 y）
  // image y=1 在 figure 底部 → 对应 page_y_top = fy1（最小 y）
  const x1 = fx1 + lx1 * fw
  const x2 = fx1 + lx2 * fw
  const y_top1 = fy2 - ly1 * fh  // 对应 image bbox 顶部
  const y_top2 = fy2 - ly2 * fh  // 对应 image bbox 底部
  return [x1, y_top1, x2, y_top2]
}

/** 用 file path basename 做模糊匹配 — 适应 persist 时 absolute path 与 API basename 的差异 */
function basename(p: string | null | undefined): string {
  if (!p) return ''
  return p.split(/[\\/]/).pop() ?? ''
}

export function CorefBboxOverlay(props: CorefBboxOverlayProps): React.ReactElement | null {
  const {
    labels, predictions, threshold,
    containerWidth, containerHeight, originalHeight, scale,
    figureBoxes,
    onMolClick, onMolContextMenu, onLabelClick,
  } = props

  // 过滤低于阈值的 prediction
  const visiblePreds = useMemo(
    () => predictions.filter(p => p.confidence >= threshold),
    [predictions, threshold],
  )

  const predColor = (p: CorefPrediction): string =>
    SOURCE_COLORS[p.source] ?? LABEL_DEFAULT_COLOR

  // 为每个 prediction 找对应的 label（按 label_id 匹配）
  const labelById = useMemo(() => {
    const m = new Map<number, FigureLabel>()
    for (const l of labels) m.set(l.id, l)
    return m
  }, [labels])

  /** 把 record 的 bbox (figure 0-1) 转成 CSS {x,y,w,h} — 走 pdfToCss */
  const projectToCss = (
    imgBbox: [number, number, number, number] | null | undefined,
    imagePath: string | null | undefined,
  ): { x: number; y: number; w: number; h: number } | null => {
    if (!imgBbox) return null
    const figBbox = figureBoxes.get(basename(imagePath))
    if (!figBbox) return null
    const pageBbox = projectFigureBboxToPage(imgBbox, figBbox)
    if (!pageBbox) return null
    return pdfToCss(pageBbox, originalHeight, scale)
  }

  if (containerWidth <= 0 || containerHeight <= 0) return null

  // 渲染前先预计算（避免在 JSX 中重复计算）
  const labelBoxes = useMemo(() => {
    return labels.map(l => ({
      label: l,
      box: projectToCss(l.label_bbox, l.image_path),
    })).filter(e => e.box !== null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [labels, figureBoxes, originalHeight, scale])

  const predictionBoxes = useMemo(() => {
    return visiblePreds.map(p => ({
      pred: p,
      molBox: projectToCss(p.mol_bbox, p.image_path ?? labelById.get(p.label_id ?? -1)?.image_path ?? null),
      labelBox: projectToCss(p.label_bbox, p.image_path ?? labelById.get(p.label_id ?? -1)?.image_path ?? null),
    })).filter(e => e.molBox !== null || e.labelBox !== null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visiblePreds, figureBoxes, labelById, originalHeight, scale])

  // 统计不可投影的预测数（用于 UI 提示）
  const unprojected = predictions.length - predictionBoxes.length

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
        {predictionBoxes.map(({ pred: p, molBox, labelBox }) => {
          if (!molBox || !labelBox) return null
          const mcx = molBox.x + molBox.w / 2
          const mcy = molBox.y + molBox.h / 2
          const lcx = labelBox.x + labelBox.w / 2
          const lcy = labelBox.y + labelBox.h / 2
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

        {/* Label 框（投影到 PDF 页面坐标） */}
        {labelBoxes.map(({ label: l, box }) => {
          if (!box) return null
          const visible = visiblePreds.some(
            p => p.label_id === l.id && p.confidence >= threshold,
          )
          if (!visible && threshold > 0) return null
          return (
            <rect
              key={`label-${l.id}`}
              x={box.x}
              y={box.y}
              width={box.w}
              height={box.h}
              fill="none"
              stroke={LABEL_DEFAULT_COLOR}
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

        {/* Mol 框（投影到 PDF 页面坐标） */}
        {predictionBoxes.map(({ pred: p, molBox }) => {
          if (!molBox) return null
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
              x={molBox.x}
              y={molBox.y}
              width={molBox.w}
              height={molBox.h}
              fill={color}
              fillOpacity={0.1}
              stroke={color}
              strokeWidth={2}
              style={{ pointerEvents: 'auto', cursor: onMolClick ? 'pointer' : 'default' }}
              onClick={(e) => { e.stopPropagation(); onMolClick?.(clickInfo) }}
              onContextMenu={(e) => { e.stopPropagation(); onMolContextMenu?.(clickInfo, e) }}
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
        title={`显示 ${predictionBoxes.length} / 共有 ${predictions.length}`}
      >
        <span>显示 {predictionBoxes.length} / 共有 {predictions.length}</span>
        {visiblePreds.length > 0 && (
          <span style={{ marginLeft: 8, fontSize: 11, opacity: 0.7 }}>
            (阈值 {threshold.toFixed(2)})
          </span>
        )}
        {unprojected > 0 && (
          <span style={{ marginLeft: 8, fontSize: 11, color: '#fbbf24' }} title="缺少该 figure 在页面上的 bbox_pdf 投影">
            ⚠ {unprojected} 未投影
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

export default CorefBboxOverlay
