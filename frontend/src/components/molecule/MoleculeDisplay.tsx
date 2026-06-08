import { useState, useEffect, useRef, lazy, Suspense } from 'react'
import { motion } from 'framer-motion'
import { CheckIcon, AlertIcon, InfoIcon } from '../icons'
import { invoke } from '@tauri-apps/api/core'
import { validateSmiles, type ValidationIssue } from '../../api/tauri/molecule'

const MermaidCode = lazy(() =>
  import('../ui/MermaidCode').then(m => ({ default: m.MermaidCode }))
)

// ============================================================================
// 类型
// ============================================================================

export interface MoleculeDisplayProps {
  /** E-SMILES / SMILES 字符串 */
  smiles: string
  /** 显示模式 */
  mode?: 'view' | 'edit' | 'compare'
  /** 分子名称 */
  name?: string
  /** 渲染尺寸（px）*/
  size?: number
  /** 背景色 */
  background?: string
  /** 显示元数据（分子式/分子量）*/
  showMetadata?: boolean
  /** 置信度（0-1，用于显示来源可信度）*/
  confidence?: number
  /** 来源说明 */
  source?: string
  /** 编辑回调（mode='edit'）*/
  onChange?: (newSmiles: string) => void
  /** 验证回调：是否化学结构有效 */
  onValidate?: (isValid: boolean, message?: string) => void
  /** 自定义类名 */
  className?: string
  style?: React.CSSProperties
}

// ============================================================================
// 辅助函数
// ============================================================================

/** SMILES → PubChem 图片 URL（最简方案，无需后端）*/
function smilesToImgUrl(smiles: string, size = 300): string {
  const encoded = encodeURIComponent(smiles)
  return `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/${encoded}/PNG?image_size=${size}x${size}`
}

/** SMILES 基础验证：检查字符集（前端快速失败，与后端 chematic 解析互补）*/
function basicValidate(smiles: string): { valid: boolean; message?: string } {
  if (!smiles || smiles.trim().length === 0) {
    return { valid: false, message: 'SMILES 为空' }
  }
  if (smiles.length > 200) {
    return { valid: false, message: 'SMILES 过长（>200字符）' }
  }
  if (!/^[A-Za-z0-9@+\-\[\]()\\/#%=.:]+$/.test(smiles.trim())) {
    return { valid: false, message: '包含非法字符' }
  }
  return { valid: true }
}

/** 估算分子式（非常简化版）*/
function estimateFormula(smiles: string): string {
  const atomRegex = /[A-Z][a-z]?/g
  const atoms = new Map<string, number>()
  let match
  while ((match = atomRegex.exec(smiles)) !== null) {
    const atom = match[0]
    if (['Cl', 'Br'].includes(atom)) continue
    if (atom === 'H') continue // 隐式 H
    atoms.set(atom, (atoms.get(atom) ?? 0) + 1)
  }
  if (atoms.size === 0) return smiles
  return Array.from(atoms.entries())
    .sort(([a], [b]) => {
      // Hill 系统：C 优先，其他按字母
      if (a === 'C') return -1
      if (b === 'C') return 1
      return a.localeCompare(b)
    })
    .map(([atom, count]) => atom + (count > 1 ? count : ''))
    .join('')
}

/** 估算分子量（粗略）*/
const ATOMIC_WEIGHTS: Record<string, number> = {
  H: 1.008, C: 12.011, N: 14.007, O: 15.999,
  F: 18.998, P: 30.974, S: 32.065, Cl: 35.453,
  Br: 79.904, I: 126.904,
}
function estimateMW(smiles: string): number {
  const atomRegex = /[A-Z][a-z]?/g
  let mw = 0
  let match
  while ((match = atomRegex.exec(smiles)) !== null) {
    const atom = match[0]
    if (atom === 'H') continue
    mw += ATOMIC_WEIGHTS[atom] ?? 0
  }
  return Math.round(mw * 10) / 10
}

// ============================================================================
// 置信度指示器
// ============================================================================

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? 'var(--success)' : pct >= 50 ? 'var(--warning)' : 'var(--danger)'
  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '2px 8px',
      background: 'rgba(255,255,255,0.9)',
      border: `1px solid ${color}`,
      borderRadius: 12,
      fontSize: 11,
      fontWeight: 600,
      color,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
      置信度 {pct}%
    </div>
  )
}

// ============================================================================
// 主组件
// ============================================================================

/**
 * MoleculeDisplay 分子显示组件。
 *
 * 支持三种模式：
 * - view:   只读显示
 * - edit:   可编辑（手动矫正 SMILES）
 * - compare:对比模式（多张图并排）
 *
 * O-03：通过 `validateSmiles`（Rust chematic 解析）防抖校验，失败时
 *       边框标红 + 内联错误提示，错误信息不静默吞错。
 */
export default function MoleculeDisplay({
  smiles,
  mode = 'view',
  name,
  size = 240,
  background = 'white',
  showMetadata = false,
  confidence,
  source,
  onChange,
  onValidate,
  className,
  style,
}: MoleculeDisplayProps) {
  const [imgError, setImgError] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [draftSmiles, setDraftSmiles] = useState(smiles)
  const [validating, _setValidating] = useState(false)
  const [validationMsg, setValidationMsg] = useState<string | null>(null)
  const [showMoleCode, setShowMoleCode] = useState(false)
  const [moleCodeText, setMoleCodeText] = useState<string | null>(null)
  const [moleCodeLoading, setMoleCodeLoading] = useState(false)
  const [moleCodeError, setMoleCodeError] = useState<string | null>(null)
  // O-03：后端结构校验（Rust chematic 解析）— 用于标红 + 错误提示
  const [backendIssue, setBackendIssue] = useState<ValidationIssue | null>(null)
  const [backendLoading, setBackendLoading] = useState(false)
  const backendTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // 当外部 smiles 变化时同步
  useEffect(() => {
    setDraftSmiles(smiles)
    setImgError(false)
  }, [smiles])

  // O-03：防抖触发后端结构校验 — 任何 smiles 变化都校验（无论是否编辑）
  useEffect(() => {
    if (backendTimerRef.current) clearTimeout(backendTimerRef.current)
    setBackendLoading(true)
    backendTimerRef.current = setTimeout(async () => {
      try {
        const resp = await validateSmiles(smiles)
        const errorIssue = resp.issues.find(i => i.severity === 'error') ?? null
        setBackendIssue(errorIssue)
      } catch (err) {
        // O-03：失败时不再静默吞错 — 把网络错误暴露为 issue
        const message = err instanceof Error ? err.message : String(err)
        setBackendIssue({
          code: 'NETWORK',
          severity: 'error',
          message: `结构校验失败：${message}`,
        })
      } finally {
        setBackendLoading(false)
      }
    }, 400)
    return () => {
      if (backendTimerRef.current) clearTimeout(backendTimerRef.current)
    }
  }, [smiles])

  // 初始验证（向 onValidate 回调暴露整体有效性）
  useEffect(() => {
    if (backendIssue) {
      onValidate?.(false, backendIssue.message)
    } else {
      const result = basicValidate(smiles)
      onValidate?.(result.valid, result.message)
    }
  }, [smiles, backendIssue, onValidate])

  // 获取 MoleCode
  const fetchMoleCode = async () => {
    if (moleCodeText) return
    setMoleCodeLoading(true)
    setMoleCodeError(null)
    try {
      const mermaidText = await invoke<string>('esmiles_to_molecode_cmd', {
        esmiles: smiles,
        name: name || 'Molecule',
      })
      setMoleCodeText(mermaidText)
    } catch (err) {
      setMoleCodeError(err instanceof Error ? err.message : String(err))
    } finally {
      setMoleCodeLoading(false)
    }
  }

  // 切换 MoleCode 视图
  const toggleMoleCode = () => {
    if (!showMoleCode) {
      fetchMoleCode()
    }
    setShowMoleCode(!showMoleCode)
  }

  const handleStartEdit = () => {
    setIsEditing(true)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  const handleApplyEdit = () => {
    const trimmed = draftSmiles.trim()
    const result = basicValidate(trimmed)
    if (!result.valid) {
      setValidationMsg(result.message ?? '格式错误')
      return
    }
    // O-03：等待后端校验完成，且不允许应用已知无效的 SMILES
    if (backendLoading) {
      setValidationMsg('正在校验…')
      return
    }
    if (backendIssue && backendIssue.severity === 'error') {
      setValidationMsg(backendIssue.message)
      return
    }
    onChange?.(trimmed)
    setIsEditing(false)
    setValidationMsg(null)
    setImgError(false)
  }

  const handleCancelEdit = () => {
    setDraftSmiles(smiles)
    setIsEditing(false)
    setValidationMsg(null)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleApplyEdit()
    else if (e.key === 'Escape') handleCancelEdit()
  }

  const formula = showMetadata ? estimateFormula(smiles) : null
  const mw = showMetadata ? estimateMW(smiles) : null
  const validation = basicValidate(smiles)
  // O-03：合并 local + backend 校验 — 任一失败即边框标红 + 显示错误
  const effectiveError: string | null =
    validationMsg
    ?? (validation.valid ? null : validation.message)
    ?? (backendIssue?.severity === 'error' ? backendIssue.message : null)

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        background: 'var(--bg-surface)',
        border: `1px solid ${effectiveError ? 'var(--danger)' : 'var(--border)'}`,
        borderRadius: 12,
        padding: 12,
        ...style,
      }}
    >
      {/* 顶部元信息 */}
      {(name || confidence !== undefined || source) && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
        }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {name && (
              <div style={{
                fontSize: 14,
                fontWeight: 600,
                color: 'var(--text-primary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }} title={name}>
                {name}
              </div>
            )}
            {source && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                来源：{source}
              </div>
            )}
          </div>
          {confidence !== undefined && <ConfidenceBadge value={confidence} />}
        </div>
      )}

      {/* 分子图像 / 编辑器 */}
      <div style={{
        position: 'relative',
        background,
        borderRadius: 8,
        overflow: 'hidden',
        minHeight: size,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        {isEditing ? (
          <div style={{ width: '100%', padding: 12 }}>
            <input
              ref={inputRef}
              type="text"
              value={draftSmiles}
              onChange={e => { setDraftSmiles(e.target.value); setValidationMsg(null) }}
              onKeyDown={handleKeyDown}
              placeholder="输入 SMILES..."
              disabled={validating}
              style={{
                width: '100%',
                padding: '8px 10px',
                fontFamily: 'monospace',
                fontSize: 13,
                background: 'var(--bg-base)',
                border: `1px solid ${effectiveError ? 'var(--danger)' : 'var(--border)'}`,
                borderRadius: 6,
                color: 'var(--text-primary)',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
            {effectiveError && (
              <div style={{
                marginTop: 6,
                fontSize: 11,
                color: 'var(--danger)',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}>
                <AlertIcon size={12} /> {effectiveError}
                {backendLoading && <span style={{ color: 'var(--text-muted)' }}>（校验中…）</span>}
              </div>
            )}
            <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
              <button
                onClick={handleApplyEdit}
                disabled={validating}
                style={{
                  flex: 1,
                  padding: '6px 10px',
                  background: 'var(--accent)',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: 500,
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 4,
                }}
              >
                <CheckIcon size={12} /> 应用
              </button>
              <button
                onClick={handleCancelEdit}
                disabled={validating}
                style={{
                  flex: 1,
                  padding: '6px 10px',
                  background: 'var(--bg-elevated)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  fontSize: 12,
                  cursor: 'pointer',
                }}
              >
                取消
              </button>
            </div>
          </div>
        ) : showMoleCode ? (
          <div style={{ width: '100%', padding: 8 }}>
            {moleCodeLoading ? (
              <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>
                Loading MoleCode...
              </div>
            ) : moleCodeError ? (
              <div style={{ textAlign: 'center', padding: 24, color: 'var(--danger, #e74c3c)', fontSize: 12 }}>
                {moleCodeError}
              </div>
            ) : moleCodeText ? (
              <Suspense fallback={<div>Loading...</div>}>
                <MermaidCode code={moleCodeText} />
              </Suspense>
            ) : null}
          </div>
        ) : imgError ? (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 8,
            padding: 24,
            color: 'var(--text-muted)',
            textAlign: 'center',
          }}>
            <div style={{ opacity: 0.4, marginBottom: 4 }}>
              <svg width={48} height={48} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="2" width="20" height="20" rx="3" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <path d="m21 15-5-5L5 21" />
              </svg>
            </div>
            <div style={{ fontSize: 12, fontWeight: 500 }}>网络不可用</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', opacity: 0.7 }}>
              {validation.valid ? '无法加载分子结构图，请检查网络连接' : (validation.message ?? '无法渲染此 SMILES')}
            </div>
            <button
              onClick={() => setImgError(false)}
              style={{
                marginTop: 4,
                padding: '4px 12px',
                fontSize: 11,
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                color: 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              重试
            </button>
          </div>
        ) : !validation.valid ? (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 8,
            padding: 24,
            color: 'var(--text-muted)',
            textAlign: 'center',
          }}>
            <InfoIcon size={32} />
            <div style={{ fontSize: 12 }}>{validation.message}</div>
          </div>
        ) : backendIssue && backendIssue.severity === 'error' && !backendLoading ? (
          // O-03：后端校验失败占位（local basicValidate 通过但 chematic 解析失败）
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 8,
            padding: 24,
            color: 'var(--danger)',
            textAlign: 'center',
          }}>
            <AlertIcon size={32} />
            <div style={{ fontSize: 12, fontWeight: 600 }}>化学结构无效</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              {backendIssue.message}
            </div>
          </div>
        ) : (
          <motion.img
            key={smiles}
            src={smilesToImgUrl(smiles, size)}
            alt={name ?? smiles}
            width={size}
            height={size}
            onError={() => setImgError(true)}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
            style={{ display: 'block', maxWidth: '100%', height: 'auto' }}
          />
        )}
      </div>

      {/* SMILES 文本 */}
      <div style={{
        fontFamily: 'monospace',
        fontSize: 11,
        color: effectiveError ? 'var(--danger)' : 'var(--text-muted)',
        padding: '4px 8px',
        background: effectiveError ? 'rgba(239, 68, 68, 0.06)' : 'var(--bg-base)',
        border: `1px solid ${effectiveError ? 'rgba(239, 68, 68, 0.3)' : 'transparent'}`,
        borderRadius: 4,
        wordBreak: 'break-all',
        maxHeight: 60,
        overflow: 'auto',
      }}>
        {smiles}
      </div>

      {/* 元数据 */}
      {showMetadata && (formula || mw) && (
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 11,
          color: 'var(--text-secondary)',
          padding: '4px 0',
          borderTop: '1px solid var(--border)',
        }}>
          {formula && <span>分子式：<strong style={{ fontFamily: 'monospace' }}>{formula}</strong></span>}
          {mw && <span>分子量：<strong>{mw} g/mol</strong></span>}
        </div>
      )}

      {/* 工具栏 */}
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          onClick={toggleMoleCode}
          title="MoleCode 图视图"
          style={{
            padding: '6px 10px',
            background: showMoleCode ? 'var(--accent)' : 'var(--bg-elevated)',
            color: showMoleCode ? 'white' : 'var(--text-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            fontSize: 12,
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 4,
          }}
        >
          <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <circle cx="12" cy="12" r="10" />
            <path d="M8 12h8" />
            <path d="M12 8v8" />
          </svg>
          MoleCode
        </button>

        {mode === 'edit' && !isEditing && (
          <button
            onClick={handleStartEdit}
            style={{
              flex: 1,
              padding: '6px 10px',
              background: 'var(--bg-elevated)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 500,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 4,
            }}
          >
            <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
            手动编辑
          </button>
        )}
      </div>
    </div>
  )
}
