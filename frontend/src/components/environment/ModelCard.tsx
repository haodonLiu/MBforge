import { CheckIcon, TrashIcon, DownloadIcon } from '../icons'
import Button from '../ui/Button'
import type { ModelInfo } from './types'

export interface ModelCardProps {
  model: ModelInfo
  onDownload: (id: string) => void
  onDelete: (id: string) => void
}

const TYPE_COLORS: Record<string, { bg: string; text: string }> = {
  embedding: { bg: 'rgba(59, 130, 246, 0.1)', text: '#3b82f6' },
  reranker: { bg: 'rgba(168, 85, 247, 0.1)', text: '#a855f7' },
  detection: { bg: 'rgba(245, 158, 11, 0.1)', text: '#f59e0b' },
}

/**
 * 模型条目卡片.
 *
 * 展示模型元数据 + 状态 + 操作按钮 (Download / Delete / Downloading).
 * 状态由 `model.downloading / downloaded` 推导.
 */
export default function ModelCard({ model, onDownload, onDelete }: ModelCardProps) {
  const typeColor = TYPE_COLORS[model.type] || TYPE_COLORS.detection
  const displaySize = model.downloaded ? model.actual_size_mb : model.size_mb
  const sizeLabel = model.downloaded ? `${displaySize} MB` : `~${displaySize} MB`

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 16px',
        background: 'var(--bg-base)',
        borderRadius: '8px',
        border: model.downloaded ? '1px solid var(--success)' : '1px solid var(--border)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: 0 }}>
        <div
          style={{
            width: '24px',
            height: '24px',
            borderRadius: '50%',
            background: model.downloaded ? 'var(--success)' : 'var(--text-muted)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            flexShrink: 0,
          }}
        >
          {model.downloaded ? <CheckIcon size={12} /> : null}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: '14px',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            {model.name}
            <span
              style={{
                fontSize: '10px',
                padding: '2px 6px',
                background: typeColor.bg,
                color: typeColor.text,
                borderRadius: '4px',
              }}
            >
              {model.type}
            </span>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
            {model.description}
          </div>
          {model.downloaded && (
            <div style={{ fontSize: '11px', color: 'var(--success)', marginTop: '4px' }}>
              Downloaded: {model.actual_size_mb} MB
              {model.location.primary && ` from ${model.location.primary}`}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginLeft: '16px' }}>
        <span
          style={{
            fontSize: '12px',
            color: model.downloaded ? 'var(--success)' : 'var(--text-muted)',
            whiteSpace: 'nowrap',
            fontWeight: model.downloaded ? 500 : 400,
          }}
        >
          {sizeLabel}
        </span>

        {model.downloading ? (
          <Button variant="secondary" size="sm" disabled>
            Downloading...
          </Button>
        ) : model.downloaded ? (
          <Button variant="danger" size="sm" icon={<TrashIcon size={12} />} onClick={() => onDelete(model.id)}>
            Delete
          </Button>
        ) : (
          <Button variant="primary" size="sm" icon={<DownloadIcon size={12} />} onClick={() => onDownload(model.id)}>
            Download
          </Button>
        )}
      </div>
    </div>
  )
}
