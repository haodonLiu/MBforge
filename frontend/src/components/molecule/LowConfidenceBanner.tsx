/**
 * LowConfidenceBanner — 项目级"低置信度分子"全局提醒。
 *
 * 用途：
 *   - 嵌于 MoleculeReviewPanel 顶部，列出 `confidence < threshold` 的分子
 *   - 提示"还有 N 个低置信度分子待复核"，引导用户优先处理
 *
 * 数据来源：
 *   - `Molecule.confidence`（检测阶段，0-1）
 *   - 阈值来自 `useConfidenceThreshold` hook（与 O-01 矫正流程共用）
 *
 * 行为：
 *   - 当 lowConfidenceCount === 0 — 不渲染（避免无谓打扰）
 *   - 当 lowConfidenceCount > 0 — 渲染黄色警告条 + 展开按钮（可选列出前 5 个）
 */

import { useState } from 'react'
import { AlertIcon } from '../icons'
import { useConfidenceThreshold } from '../../hooks/useConfidenceThreshold'
import type { Molecule } from '../MoleculeReviewPanel'

export interface LowConfidenceBannerProps {
  /** 当前 review 批次的分子列表 */
  molecules: Molecule[]
  /** 跳转到指定分子（点击 banner 内分子项触发）*/
  onSelect?: (moleculeId: string) => void
  style?: React.CSSProperties
  className?: string
}

export default function LowConfidenceBanner({
  molecules,
  onSelect,
  style,
  className,
}: LowConfidenceBannerProps) {
  const [threshold] = useConfidenceThreshold()
  const [expanded, setExpanded] = useState(false)

  // 只统计 pending 状态的低置信度（已 accept/reject 的不再需要提醒）
  const lowConfidence = molecules.filter(
    m => m.status === 'pending' && m.confidence < threshold,
  )
  const total = lowConfidence.length

  if (total === 0) return null

  const shown = expanded ? lowConfidence : lowConfidence.slice(0, 5)
  const hiddenCount = lowConfidence.length - shown.length

  return (
    <div
      className={className}
      role="alert"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: '10px 14px',
        background: 'rgba(245, 158, 11, 0.1)',
        border: '1px solid rgba(245, 158, 11, 0.3)',
        borderRadius: 8,
        color: 'var(--warning)',
        fontSize: 13,
        ...style,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <AlertIcon size={16} />
        <span style={{ flex: 1, fontWeight: 600 }}>
          低置信度提醒：{total} 个分子置信度低于阈值 {Math.round(threshold * 100)}%
        </span>
        {lowConfidence.length > 5 && (
          <button
            onClick={() => setExpanded(v => !v)}
            style={{
              background: 'transparent',
              border: '1px solid rgba(245, 158, 11, 0.4)',
              borderRadius: 6,
              padding: '2px 8px',
              fontSize: 11,
              color: 'var(--warning)',
              cursor: 'pointer',
            }}
            title={expanded ? '收起列表' : `展开剩余 ${hiddenCount} 个`}
          >
            {expanded ? '收起' : `+${hiddenCount} 更多`}
          </button>
        )}
      </div>

      {/* 列表（仅展示前 5 个，点击触发 onSelect）*/}
      <ul
        style={{
          margin: 0,
          padding: '4px 0 0 0',
          listStyle: 'none',
          display: 'flex',
          flexWrap: 'wrap',
          gap: 6,
        }}
      >
        {shown.map(m => (
          <li key={m.id}>
            <button
              onClick={() => onSelect?.(m.id)}
              disabled={!onSelect}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                padding: '2px 8px',
                background: 'rgba(255,255,255,0.6)',
                border: '1px solid rgba(245, 158, 11, 0.3)',
                borderRadius: 4,
                fontSize: 11,
                fontFamily: 'monospace',
                color: 'var(--text-primary)',
                cursor: onSelect ? 'pointer' : 'default',
                maxWidth: 280,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={onSelect ? `跳转到 ${m.name || m.smiles}` : (m.name || m.smiles)}
            >
              <span style={{ color: 'var(--warning)', fontWeight: 600 }}>
                {Math.round(m.confidence * 100)}%
              </span>
              <span style={{ color: 'var(--text-secondary)' }}>
                {m.name || m.smiles}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
