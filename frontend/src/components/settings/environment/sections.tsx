import { PageContainer, Skeleton, Card, SectionTitle } from '@/components/ui'
import ResponsiveStatGrid from '@/components/ui/ResponsiveStatGrid'
import PathCard from './PathCard'
import type { ModelPaths } from './types'

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
          <Card key={i} padding="20px 16px" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <Skeleton variant="text" style={{ width: '60%', height: '10px' }} />
            <Skeleton variant="text" style={{ width: '80%', height: '24px' }} />
            <Skeleton variant="text" style={{ width: '50%', height: '10px' }} />
          </Card>
        ))}
      </ResponsiveStatGrid>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {[0, 1].map(i => (
          <Card key={i}>
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
          </Card>
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
    <Card padding="16px 20px" style={{ marginBottom: '24px' }}>
      <SectionTitle style={{ marginBottom: '16px' }}>
        Model Cache Paths
      </SectionTitle>

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
    </Card>
  )
}

// ============================================================================
// AI 模型下载区块已迁移至 Settings → Models tab (`ModelsTab.tsx`)。
// 环境栏目 (SystemTab) 仅展示汇总统计，不再重复展示下载 UI。
// ============================================================================
