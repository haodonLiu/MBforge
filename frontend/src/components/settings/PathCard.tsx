import { FolderIcon, EditIcon } from '@/components/icons'
import Button from '@/components/ui/Button'

export interface PathCardProps {
  title: string
  path: string
  exists: boolean
  size_mb: number
  envVar?: string
  isEditing?: boolean
  editValue?: string
  onEdit?: () => void
  onSave?: () => void
  onCancel?: () => void
  onChange?: (value: string) => void
}

/**
 * 路径 / 缓存目录展示卡片.
 *
 * 显示当前路径 + 是否存在 + 已用空间;支持行内编辑 (用于配置 HF/ModelScope 缓存目录).
 */
export default function PathCard({
  title,
  path,
  exists,
  size_mb,
  envVar,
  isEditing = false,
  editValue = '',
  onEdit,
  onSave,
  onCancel,
  onChange,
}: PathCardProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 16px',
        background: 'var(--bg-base)',
        borderRadius: '8px',
        border: '1px solid var(--border)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: 0 }}>
        <div
          style={{
            width: '24px',
            height: '24px',
            borderRadius: '6px',
            background: exists ? 'var(--success)' : 'var(--bg-surface)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: exists ? 'white' : 'var(--text-muted)',
            flexShrink: 0,
          }}
        >
          <FolderIcon size={14} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: '13px',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            {title}
            {envVar && (
              <span
                style={{
                  fontSize: '10px',
                  padding: '2px 6px',
                  background: 'var(--bg-surface)',
                  borderRadius: '4px',
                  color: 'var(--text-muted)',
                }}
              >
                {envVar}
              </span>
            )}
          </div>
          {isEditing ? (
            <input
              type="text"
              value={editValue}
              onChange={e => onChange?.(e.target.value)}
              style={{
                width: '100%',
                marginTop: '6px',
                padding: '6px 10px',
                background: 'var(--bg-surface)',
                border: '1px solid var(--accent)',
                borderRadius: '6px',
                fontSize: '12px',
                color: 'var(--text-primary)',
              }}
            />
          ) : (
            <div
              style={{
                fontSize: '11px',
                color: 'var(--text-muted)',
                marginTop: '2px',
                wordBreak: 'break-all',
              }}
            >
              {path}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginLeft: '16px' }}>
        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          {exists ? `${size_mb} MB` : 'Not found'}
        </span>

        {isEditing ? (
          <div style={{ display: 'flex', gap: '4px' }}>
            <Button variant="primary" size="sm" onClick={onSave}>
              Save
            </Button>
            <Button variant="secondary" size="sm" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        ) : onEdit ? (
          <Button variant="secondary" size="sm" icon={<EditIcon size={12} />} onClick={onEdit}>
            Edit
          </Button>
        ) : null}
      </div>
    </div>
  )
}
