import { useState } from 'react'
import { motion } from 'framer-motion'
import MoleculeDisplay from './MoleculeDisplay'
import Button from '../ui/Button'
import Badge from '../ui/Badge'
import { CheckIcon, XIcon, AlertIcon, ChevronLeftIcon, ChevronRightIcon } from '../icons'

// ============================================================================
// 类型
// ============================================================================

export interface CorrectionItem {
  /** 唯一 ID */
  id: string
  /** 原始 OCR 识别的 SMILES */
  ocrSmiles: string
  /** OCR 识别置信度（0-1）*/
  ocrConfidence: number
  /** 用户修正后的 SMILES（可选）*/
  correctedSmiles?: string
  /** 来自文献的图像（裁剪出来的）*/
  sourceImage?: string
  /** 分子名称 */
  name?: string
  /** 来源文献 */
  sourceDoc?: string
  /** 上下文文本 */
  context?: string
  /** 状态 */
  status?: 'pending' | 'confirmed' | 'rejected' | 'corrected'
}

export interface CorrectionPanelProps {
  items: CorrectionItem[]
  /** 完成回调：返回每项的最终 SMILES */
  onComplete: (results: Array<{ id: string; finalSmiles: string; status: 'confirmed' | 'rejected' | 'corrected' }>) => void
  /** 单项状态变化 */
  onItemChange?: (id: string, finalSmiles: string, status: CorrectionItem['status']) => void
  /** 是否显示文献图像（默认 true）*/
  showSourceImage?: boolean
  /** 一次显示几项（默认 1 = 逐个矫正）*/
  batchSize?: number
  /** 自定义类名 */
  className?: string
  style?: React.CSSProperties
}

// ============================================================================
// 子组件
// ============================================================================

function StatusBadge({ status }: { status: CorrectionItem['status'] }) {
  switch (status) {
    case 'confirmed':
      return <Badge variant="success" dot>已确认</Badge>
    case 'corrected':
      return <Badge variant="info" dot>已修正</Badge>
    case 'rejected':
      return <Badge variant="danger" dot>已拒绝</Badge>
    default:
      return <Badge variant="warning" dot>待处理</Badge>
  }
}

function SmilesDiff({ before, after }: { before: string; after: string }) {
  if (before === after) return null
  // 简单的字符级 diff（找第一个不同的位置）
  let i = 0
  while (i < before.length && i < after.length && before[i] === after[i]) i++

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      padding: 8,
      background: 'var(--bg-base)',
      borderRadius: 6,
      fontSize: 11,
      fontFamily: 'monospace',
    }}>
      <div>
        <span style={{ color: 'var(--text-muted)' }}>原：</span>
        <span style={{ color: 'var(--text-primary)' }}>{before.slice(0, i)}</span>
        <span style={{ color: 'var(--danger)', textDecoration: 'line-through' }}>{before.slice(i)}</span>
      </div>
      <div>
        <span style={{ color: 'var(--text-muted)' }}>新：</span>
        <span style={{ color: 'var(--text-primary)' }}>{after.slice(0, i)}</span>
        <span style={{ color: 'var(--success)', fontWeight: 600 }}>{after.slice(i)}</span>
      </div>
    </div>
  )
}

// ============================================================================
// 主组件
// ============================================================================

/**
 * CorrectionPanel 分子矫正流程。
 *
 * 工作流：
 *   1. 显示 OCR 识别结果 + 文献原图（并排）
 *   2. 用户选择：确认 / 修正 / 拒绝
 *   3. 修正模式下可手动编辑 SMILES
 *   4. 完成后回调，通知上游保存
 */
export default function CorrectionPanel({
  items,
  onComplete,
  onItemChange,
  showSourceImage = true,
  className,
  style,
}: CorrectionPanelProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [decisions, setDecisions] = useState<Record<string, {
    status: 'confirmed' | 'rejected' | 'corrected'
    finalSmiles: string
  }>>({})

  const total = items.length
  const current = items[currentIndex]
  const currentDecision = decisions[current?.id ?? '']
  const isLast = currentIndex === total - 1
  const isFirst = currentIndex === 0

  if (!current) {
    return (
      <div className={className} style={{
        padding: 40,
        textAlign: 'center',
        color: 'var(--text-muted)',
        ...style,
      }}>
        没有待矫正的分子
      </div>
    )
  }

  const currentFinalSmiles = currentDecision?.finalSmiles ?? current.correctedSmiles ?? current.ocrSmiles
  const currentStatus: CorrectionItem['status'] = currentDecision?.status ?? current.status ?? 'pending'
  const isOcrConfident = current.ocrConfidence >= 0.8

  const updateDecision = (status: 'confirmed' | 'rejected' | 'corrected', smiles?: string) => {
    const finalSmiles = smiles ?? currentFinalSmiles
    setDecisions(prev => ({
      ...prev,
      [current.id]: { status, finalSmiles },
    }))
    onItemChange?.(current.id, finalSmiles, status)
  }

  const handleSmilesEdit = (newSmiles: string) => {
    // 任何编辑都标记为 corrected
    updateDecision('corrected', newSmiles)
  }

  const handleConfirm = () => {
    updateDecision('confirmed', currentFinalSmiles)
  }

  const handleReject = () => {
    updateDecision('rejected', currentFinalSmiles)
  }

  const goPrev = () => {
    if (!isFirst) setCurrentIndex(i => i - 1)
  }

  const goNext = () => {
    if (!isLast) setCurrentIndex(i => i + 1)
  }

  const handleFinish = () => {
    // 自动决定未处理项
    const results = items.map(item => {
      const d = decisions[item.id]
      if (d) {
        return { id: item.id, finalSmiles: d.finalSmiles, status: d.status }
      }
      // 未手动处理：高置信度自动确认，低置信度标记为待复核（用 rejected 表达）
      return {
        id: item.id,
        finalSmiles: item.ocrSmiles,
        status: item.ocrConfidence >= 0.8 ? 'confirmed' as const : 'rejected' as const,
      }
    })
    onComplete(results)
  }

  const progress = ((currentIndex + 1) / total) * 100
  const decidedCount = Object.keys(decisions).length
  const allDecided = decidedCount === total

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 14,
        padding: 20,
        ...style,
      }}
    >
      {/* 顶部进度条 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
            分子矫正（{currentIndex + 1} / {total}）
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              已处理 {decidedCount} / {total}
            </span>
            <StatusBadge status={currentStatus} />
          </div>
        </div>
        <div style={{
          height: 4,
          background: 'var(--bg-elevated)',
          borderRadius: 2,
          overflow: 'hidden',
        }}>
          <motion.div
            style={{
              height: '100%',
              background: 'var(--accent)',
              borderRadius: 2,
            }}
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      </div>

      {/* 主体：并排对比 */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: showSourceImage ? '1fr 1fr 1fr' : '1fr 1fr',
        gap: 16,
      }}>
        {/* 1. 文献原图 */}
        {showSourceImage && (
          <div style={{
            background: 'var(--bg-base)',
            border: '1px solid var(--border)',
            borderRadius: 10,
            padding: 12,
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}>
            <div style={{
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              letterSpacing: 0.5,
            }}>
              文献原图
            </div>
            {current.sourceImage ? (
              <div style={{
                background: 'white',
                borderRadius: 6,
                padding: 8,
                minHeight: 200,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <img
                  src={current.sourceImage}
                  alt="来源图像"
                  style={{ maxWidth: '100%', maxHeight: 280, objectFit: 'contain' }}
                />
              </div>
            ) : (
              <div style={{
                background: 'white',
                borderRadius: 6,
                minHeight: 200,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted)',
                fontSize: 12,
              }}>
                （原图不可用）
              </div>
            )}
            {current.context && (
              <div style={{
                fontSize: 11,
                color: 'var(--text-muted)',
                lineHeight: 1.5,
                padding: 8,
                background: 'var(--bg-surface)',
                borderRadius: 4,
                maxHeight: 80,
                overflow: 'auto',
              }}>
                {current.context}
              </div>
            )}
          </div>
        )}

        {/* 2. OCR 识别结果 */}
        <MoleculeDisplay
          smiles={current.ocrSmiles}
          name="OCR 识别结果"
          source={`置信度 ${Math.round(current.ocrConfidence * 100)}%`}
          confidence={current.ocrConfidence}
          showMetadata
          mode="view"
        />

        {/* 3. 当前 / 修正结果 */}
        <div style={{ position: 'relative' }}>
          <MoleculeDisplay
            smiles={currentFinalSmiles}
            name={current.name ?? '最终结果'}
            source={currentDecision?.status === 'corrected' ? '人工修正' : '待定'}
            confidence={currentDecision?.status === 'corrected' ? 1.0 : current.ocrConfidence}
            showMetadata
            mode="edit"
            onChange={handleSmilesEdit}
          />
          {currentStatus === 'corrected' && current.ocrSmiles !== currentFinalSmiles && (
            <div style={{ marginTop: 8 }}>
              <SmilesDiff before={current.ocrSmiles} after={currentFinalSmiles} />
            </div>
          )}
        </div>
      </div>

      {/* 低置信度提示 */}
      {!isOcrConfident && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '10px 14px',
          background: 'rgba(245, 158, 11, 0.1)',
          border: '1px solid rgba(245, 158, 11, 0.3)',
          borderRadius: 8,
          color: 'var(--warning)',
          fontSize: 12,
        }}>
          <AlertIcon size={14} />
          <span>OCR 置信度较低（{Math.round(current.ocrConfidence * 100)}%），建议仔细核对分子结构。</span>
        </div>
      )}

      {/* 操作按钮 */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="secondary" size="sm" onClick={goPrev} disabled={isFirst}>
            <ChevronLeftIcon size={14} /> 上一项
          </Button>
          <Button variant="secondary" size="sm" onClick={goNext} disabled={isLast}>
            下一项 <ChevronRightIcon size={14} />
          </Button>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="danger" size="sm" onClick={handleReject}>
            <XIcon size={14} /> 拒绝
          </Button>
          <Button variant="primary" size="sm" onClick={handleConfirm}>
            <CheckIcon size={14} /> 确认
          </Button>
          <Button
            variant="primary"
            onClick={handleFinish}
            disabled={!allDecided}
            title={allDecided ? '保存所有决定' : `还有 ${total - decidedCount} 项未处理`}
          >
            完成矫正（{decidedCount}/{total}）
          </Button>
        </div>
      </div>
    </div>
  )
}
