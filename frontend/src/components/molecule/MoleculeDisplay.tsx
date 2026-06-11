import { useRef, lazy, Suspense } from 'react'
import { motion } from 'framer-motion'
import { CheckIcon, AlertIcon, InfoIcon } from '../icons'
import { smilesToImgUrl, basicValidate } from './moleculeUtils'
import ConfidenceBadge from './ConfidenceBadge'
import { useMoleculeDisplay } from '../../hooks/useMoleculeDisplay'

const MermaidCode = lazy(() =>
  import('../ui/MermaidCode').then(m => ({ default: m.MermaidCode }))
)

export interface MoleculeDisplayProps {
  smiles: string
  mode?: 'view' | 'edit' | 'compare'
  name?: string
  size?: number
  background?: string
  showMetadata?: boolean
  confidence?: number
  source?: string
  onChange?: (newSmiles: string) => void
  onValidate?: (isValid: boolean, message?: string) => void
  className?: string
  style?: React.CSSProperties
}

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
  const inputRef = useRef<HTMLInputElement>(null)

  const {
    imgError,
    setImgError,
    isEditing,
    draftSmiles,
    showMoleCode,
    moleCodeText,
    moleCodeLoading,
    moleCodeError,
    backendIssue,
    backendLoading,
    effectiveError,
    formula,
    mw,
    toggleMoleCode,
    handleStartEdit,
    handleApplyEdit,
    handleCancelEdit,
    handleKeyDown,
    setDraftSmiles,
  } = useMoleculeDisplay(smiles, name, showMetadata, onChange, onValidate)

  const startEdit = () => {
    handleStartEdit()
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  return (
    <div
      className={`mol-display ${effectiveError ? 'mol-display--error' : ''} ${className ?? ''}`}
      style={style}
    >
      {(name || confidence !== undefined || source) && (
        <div className="mol-display-header">
          <div className="mol-display-meta">
            {name && (
              <div className="mol-display-name" title={name}>
                {name}
              </div>
            )}
            {source && (
              <div className="mol-display-source">来源：{source}</div>
            )}
          </div>
          {confidence !== undefined && <ConfidenceBadge value={confidence} />}
        </div>
      )}

      <div
        className="mol-display-canvas"
        style={{ background, minHeight: size }}
      >
        {isEditing ? (
          <div className="mol-edit-form">
            <input
              ref={inputRef}
              type="text"
              value={draftSmiles}
              onChange={e => setDraftSmiles(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入 SMILES..."
              disabled={false}
              className={`mol-edit-input ${effectiveError ? 'mol-edit-input--error' : ''}`}
            />
            {effectiveError && (
              <div className="mol-edit-error">
                <AlertIcon size={12} /> {effectiveError}
                {backendLoading && <span className="mol-edit-error-hint">（校验中…）</span>}
              </div>
            )}
            <div className="mol-edit-actions">
              <button onClick={handleApplyEdit} className="mol-edit-btn mol-edit-btn--primary">
                <CheckIcon size={12} /> 应用
              </button>
              <button onClick={handleCancelEdit} className="mol-edit-btn mol-edit-btn--secondary">
                取消
              </button>
            </div>
          </div>
        ) : showMoleCode ? (
          <div className="mol-molecode-wrap">
            {moleCodeLoading ? (
              <div className="mol-molecode-loading">Loading MoleCode...</div>
            ) : moleCodeError ? (
              <div className="mol-molecode-error">{moleCodeError}</div>
            ) : moleCodeText ? (
              <Suspense fallback={<div>Loading...</div>}>
                <MermaidCode code={moleCodeText} />
              </Suspense>
            ) : null}
          </div>
        ) : imgError ? (
          <div className="mol-display-placeholder">
            <div className="mol-display-placeholder-icon">
              <svg width={48} height={48} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="2" width="20" height="20" rx="3" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <path d="m21 15-5-5L5 21" />
              </svg>
            </div>
            <div className="mol-display-placeholder-title">网络不可用</div>
            <div className="mol-display-placeholder-hint">
              {basicValidate(smiles).valid ? '无法加载分子结构图，请检查网络连接' : (basicValidate(smiles).message ?? '无法渲染此 SMILES')}
            </div>
            <button onClick={() => setImgError(false)} className="mol-display-placeholder-btn">
              重试
            </button>
          </div>
        ) : !basicValidate(smiles).valid ? (
          <div className="mol-display-placeholder">
            <InfoIcon size={32} />
            <div className="mol-display-placeholder-title">{basicValidate(smiles).message}</div>
          </div>
        ) : backendIssue && backendIssue.severity === 'error' && !backendLoading ? (
          <div className="mol-display-placeholder mol-display-placeholder--error">
            <AlertIcon size={32} />
            <div className="mol-display-placeholder-title">化学结构无效</div>
            <div className="mol-display-placeholder-hint">{backendIssue.message}</div>
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
            className="mol-display-img"
          />
        )}
      </div>

      <div className={`mol-display-smiles ${effectiveError ? 'mol-display-smiles--error' : ''}`}>
        {smiles}
      </div>

      {showMetadata && (formula || mw) && (
        <div className="mol-display-metadata">
          {formula && <span>分子式：<strong className="mol-mono">{formula}</strong></span>}
          {mw && <span>分子量：<strong>{mw} g/mol</strong></span>}
        </div>
      )}

      <div className="mol-display-toolbar">
        <button
          onClick={toggleMoleCode}
          title="MoleCode 图视图"
          className={`mol-toolbar-btn ${showMoleCode ? 'mol-toolbar-btn--active' : ''}`}
        >
          <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <circle cx="12" cy="12" r="10" />
            <path d="M8 12h8" />
            <path d="M12 8v8" />
          </svg>
          MoleCode
        </button>

        {mode === 'edit' && !isEditing && (
          <button onClick={startEdit} className="mol-toolbar-btn mol-toolbar-btn--edit">
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
