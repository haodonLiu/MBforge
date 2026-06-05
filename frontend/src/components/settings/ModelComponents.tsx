import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import Input from '../ui/Input'
import Caption from '../ui/Caption'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import Spinner from '../ui/Spinner'
import { TrashIcon } from '../icons'

// ============ ModelSelector ============
interface ModelSelectorProps {
  provider: string
  modelValue: string
  models: Record<string, { value: string; label: string }[]>
  onChange: (v: string) => void
}

export function ModelSelector({ provider, modelValue, models, onChange }: ModelSelectorProps) {
  const { t } = useTranslation()
  const [customModel, setCustomModel] = useState('')
  const options = models[provider] || []
  const isKnown = options.some(o => o.value === modelValue) || modelValue === 'custom' || modelValue === ''
  const showCustom = modelValue === 'custom' || (!isKnown && modelValue !== '')

  return (
    <>
      <select
        className="settings-select"
        value={isKnown ? modelValue : 'custom'}
        onChange={e => {
          const v = e.target.value
          if (v === 'custom') {
            onChange(customModel || modelValue)
          } else {
            onChange(v)
            setCustomModel('')
          }
        }}
      >
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
        <option value="custom">{t('models.customModel')}</option>
      </select>
      {showCustom && (
        <Input
          className="settings-input"
          value={isKnown ? customModel : modelValue}
          onChange={e => {
            setCustomModel(e.target.value)
            onChange(e.target.value)
          }}
          placeholder={t('models.enterModelName')}
          style={{ marginTop: '8px', maxWidth: '100%' }}
        />
      )}
    </>
  )
}

// ============ DownloadProgressBar ============
interface DownloadState {
  progress: number
  status: string
  error?: string
  source?: string
  fileName?: string
  fileIndex?: number
  totalFiles?: number
}

interface DownloadProgressBarProps {
  state: DownloadState
}

export function DownloadProgressBar({ state }: DownloadProgressBarProps) {
  const { t } = useTranslation()
  const progress = state.progress || 0

  return (
    <div style={{ marginTop: '8px' }}>
      {state.status === 'connecting' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Spinner size={12} />
          <Caption>{t('models.connecting')} {state.source && `(${state.source})`}</Caption>
        </div>
      )}
      {state.status === 'downloading' && (
        <>
          <div className="download-progress">
            <div className="download-progress-bar">
              <div className="download-progress-fill" style={{ width: `${progress}%` }} />
            </div>
            <span className="download-progress-text">{progress}%</span>
          </div>
          {state.fileName && (
            <Caption style={{ marginTop: '4px', display: 'block' }}>
              {state.fileName}
              {state.fileIndex && state.totalFiles && ` (${state.fileIndex}/${state.totalFiles})`}
            </Caption>
          )}
        </>
      )}
      {state.status === 'completed' && (
        <Caption color="var(--success)" style={{ display: 'block' }}>
          ✓ {t('models.downloadComplete')} {state.source && `(${state.source})`}
        </Caption>
      )}
      {state.status === 'failed' && (
        <Caption color="var(--danger)" style={{ display: 'block' }}>
          {state.error || t('models.downloadFailed')}
        </Caption>
      )}
    </div>
  )
}

// ============ ModelCard ============

interface DownloadModel {
  id: string
  name: string
  type: string
  description: string
  downloaded: boolean
  size_mb: number
  license?: string
  license_url?: string
}

interface ModelCardProps {
  model: DownloadModel
  state?: DownloadState
  isDownloading: boolean
  onDownload: () => void
  onCancel: () => void
  onRetry: () => void
}

export function ModelCard({ model, state, isDownloading, onDownload, onCancel, onRetry }: ModelCardProps) {
  const { t } = useTranslation()

  return (
    <div className="model-card">
      <div className="model-card-info">
        <div className="model-card-name">
          {model.name}
          {model.downloaded && (
            <Badge variant="success" style={{ marginLeft: '8px', fontWeight: 400 }}>
              {t('models.downloaded')}
            </Badge>
          )}
          {model.license && (
            <a
              href={model.license_url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              style={{ marginLeft: '8px', fontSize: '10px', color: 'var(--text-muted)', textDecoration: 'underline' }}
              onClick={e => e.stopPropagation()}
            >
              {model.license}
            </a>
          )}
          {model.size_mb > 0 && (
            <Caption style={{ marginLeft: '8px', fontSize: '10px' }}>
              ~{model.size_mb}MB
            </Caption>
          )}
        </div>
        <div className="model-card-desc">{model.description}</div>
        {state && state.status !== 'idle' && <DownloadProgressBar state={state} />}
      </div>
      <div className="model-card-actions">
        {!model.downloaded && !isDownloading && (
          <Button size="sm" variant="primary" onClick={onDownload}>
            {t('models.download')}
          </Button>
        )}
        {isDownloading && state?.status === 'downloading' && (
          <Button size="sm" variant="secondary" onClick={onCancel}>
            {t('common.cancel')}
          </Button>
        )}
        {state?.status === 'completed' && (
          <Caption color="var(--success)">{t('models.complete')}</Caption>
        )}
        {state?.status === 'failed' && (
          <Button size="sm" variant="secondary" onClick={onRetry}>
            {t('models.retry')}
          </Button>
        )}
      </div>
    </div>
  )
}

// ============ DownloadedModelItem ============

interface DownloadedModel {
  id: string
  name: string
  path: string
  size_mb: number
  in_catalog: boolean
}

interface DownloadedModelItemProps {
  model: DownloadedModel
  deleteConfirm: string | null
  onDeleteClick: () => void
  onConfirmDelete: () => void
  onCancelDelete: () => void
}

export function DownloadedModelItem({
  model,
  deleteConfirm,
  onDeleteClick,
  onConfirmDelete,
  onCancelDelete,
}: DownloadedModelItemProps) {
  const { t } = useTranslation()

  return (
    <div className="downloaded-model-item">
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '13px', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>{model.name}</span>
          <Caption style={{ fontSize: '11px' }}>
            {model.size_mb > 0 ? `${model.size_mb} MB` : ''}
          </Caption>
          {model.in_catalog && (
            <Badge variant="success" style={{ fontSize: '10px', fontWeight: 400 }}>
              {t('models.official')}
            </Badge>
          )}
        </div>
        <Caption style={{ marginTop: '2px', fontFamily: 'monospace', wordBreak: 'break-all', display: 'block' }}>
          {model.path}
        </Caption>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
        {deleteConfirm === model.id ? (
          <>
            <Caption color="var(--danger)">{t('models.confirmDelete')}</Caption>
            <Button size="sm" variant="secondary" onClick={onCancelDelete}>
              {t('common.cancel')}
            </Button>
            <Button size="sm" variant="primary" style={{ background: 'var(--danger)' }} onClick={onConfirmDelete}>
              {t('common.delete')}
            </Button>
          </>
        ) : (
          <button
            className="btn btn-secondary"
            style={{ padding: '4px 10px', fontSize: '11px', color: 'var(--danger)' }}
            onClick={onDeleteClick}
          >
            <TrashIcon size={12} /> {t('common.delete')}
          </button>
        )}
      </div>
    </div>
  )
}
