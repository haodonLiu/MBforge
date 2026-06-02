import { PageContainer, Skeleton } from '../ui'
import ResponsiveStatGrid from '../ui/ResponsiveStatGrid'
import PathCard from './PathCard'
import ModelCard from './ModelCard'
import type { ModelInfo, ModelPaths } from './types'

// ============================================================================
// 加载占位（首屏骨架）
// ============================================================================

export function LoadingSkeleton() {
  return (
    <PageContainer>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginBottom: '24px',
          alignItems: 'center',
        }}
      >
        <Skeleton variant="row" style={{ width: '120px', height: '28px' }} />
        <Skeleton variant="row" style={{ width: '90px', height: '32px' }} />
      </div>

      <ResponsiveStatGrid style={{ marginBottom: '24px' }}>
        {[0, 1, 2, 3].map(i => (
          <div
            key={i}
            style={{
              padding: '20px 16px',
              background: 'var(--bg-surface)',
              borderRadius: '12px',
              border: '1px solid var(--border)',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <Skeleton variant="text" style={{ width: '60%', height: '10px' }} />
            <Skeleton variant="text" style={{ width: '80%', height: '24px' }} />
            <Skeleton variant="text" style={{ width: '50%', height: '10px' }} />
          </div>
        ))}
      </ResponsiveStatGrid>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {[0, 1].map(i => (
          <div
            key={i}
            style={{
              padding: '20px',
              background: 'var(--bg-surface)',
              borderRadius: '12px',
              border: '1px solid var(--border)',
            }}
          >
            <Skeleton variant="text" style={{ width: '120px', height: '12px', marginBottom: '16px' }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {[0, 1, 2].map(j => (
                <div
                  key={j}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '12px 0',
                    borderBottom: j < 2 ? '1px solid var(--border)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <Skeleton variant="text" style={{ width: '32px', height: '32px', borderRadius: '8px' }} />
                    <Skeleton variant="text" style={{ width: '80px', height: '12px' }} />
                  </div>
                  <Skeleton variant="text" style={{ width: '60px', height: '22px', borderRadius: '20px' }} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </PageContainer>
  )
}

// ============================================================================
// 路径区块
// ============================================================================

export interface PathSectionProps {
  paths: ModelPaths | null
  editingPath: string | null
  editValue: string
  onEdit: (name: string, currentPath: string) => void
  onSave: () => void
  onCancel: () => void
  onChange: (v: string) => void
}

export function PathSection({
  paths,
  editingPath,
  editValue,
  onEdit,
  onSave,
  onCancel,
  onChange,
}: PathSectionProps) {
  return (
    <div
      style={{
        padding: '16px 20px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        marginBottom: '24px',
      }}
    >
      <div
        style={{
          fontSize: '12px',
          fontWeight: 600,
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          marginBottom: '16px',
        }}
      >
        Model Cache Paths
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {paths && (
          <>
            <PathCard
              title="MBForge"
              path={paths.mbforge.path}
              exists={paths.mbforge.exists}
              size_mb={paths.mbforge.size_mb}
              isEditing={editingPath === 'mbforge'}
              editValue={editValue}
              onEdit={() => onEdit('mbforge', paths.mbforge.path)}
              onSave={onSave}
              onCancel={onCancel}
              onChange={onChange}
            />
            <PathCard
              title="HuggingFace"
              path={paths.huggingface.path}
              exists={paths.huggingface.exists}
              size_mb={paths.huggingface.size_mb}
              envVar={paths.huggingface.env_var}
            />
            <PathCard
              title="ModelScope"
              path={paths.modelscope.path}
              exists={paths.modelscope.exists}
              size_mb={paths.modelscope.size_mb}
              envVar={paths.modelscope.env_var}
            />
          </>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// AI 模型列表区块
// ============================================================================

export interface ModelsSectionProps {
  models: ModelInfo[]
  downloadedCount: number
  onDownload: (id: string) => void
  onDelete: (id: string) => void
}

export function ModelsSection({
  models,
  downloadedCount,
  onDownload,
  onDelete,
}: ModelsSectionProps) {
  return (
    <div
      style={{
        padding: '16px 20px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
      }}
    >
      <div
        style={{
          fontSize: '12px',
          fontWeight: 600,
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          marginBottom: '16px',
        }}
      >
        AI Models ({downloadedCount}/{models.length} downloaded)
      </div>

      {models.length === 0 ? (
        <div
          style={{
            padding: '24px',
            textAlign: 'center',
            color: 'var(--text-muted)',
            fontSize: '13px',
          }}
        >
          Loading models...
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {models.map(model => (
            <ModelCard
              key={model.id}
              model={model}
              onDownload={onDownload}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}
