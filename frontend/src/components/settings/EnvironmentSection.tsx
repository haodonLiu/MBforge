import { useState, useEffect } from 'react'
import { resourcesCheck, type EnvironmentReport } from '../../api/tauri-bridge'

interface ResourceItem {
  id: string
  name: string
  type: string
  status: string
  version?: string
  local_path?: string
  size_mb: number
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'ready': return 'var(--success)'
    case 'not_found': return 'var(--warning)'
    case 'partial': return 'var(--warning)'
    default: return 'var(--danger)'
  }
}

function getStatusLabel(status: string): string {
  switch (status) {
    case 'ready': return '✓ 就绪'
    case 'not_found': return '未下载'
    case 'partial': return '部分就绪'
    default: return status
  }
}

function ResourceItem({ resource }: { resource: ResourceItem }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '6px 8px',
      borderRadius: 6,
      background: 'var(--bg-secondary, rgba(255,255,255,0.03))',
      marginBottom: 2,
    }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <span style={{ fontSize: 13, fontWeight: 500 }}>{resource.name}</span>
        {resource.local_path && (
          <span style={{
            fontSize: 11,
            color: 'var(--text-muted)',
            fontFamily: 'monospace',
            maxWidth: 300,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {resource.local_path}
          </span>
        )}
        {resource.version && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>v{resource.version}</span>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {resource.size_mb > 0 && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{resource.size_mb} MB</span>
        )}
        <span style={{ fontSize: 11, fontWeight: 600, color: getStatusColor(resource.status) }}>
          {getStatusLabel(resource.status)}
        </span>
      </div>
    </div>
  )
}

export default function EnvironmentSection() {
  const [report, setReport] = useState<EnvironmentReport | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    resourcesCheck()
      .then(r => setReport(r))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="settings-section">
        <p style={{ color: 'var(--text-muted)', padding: 16 }}>检查中...</p>
      </div>
    )
  }

  if (!report || !report.resources) {
    return (
      <div className="settings-section">
        <p style={{ color: 'var(--text-muted)', padding: 16 }}>无法获取环境信息</p>
      </div>
    )
  }

  // 按类型分组资源
  const resourcesByType: Record<string, ResourceItem[]> = {}
  report.resources.forEach(r => {
    if (!resourcesByType[r.type]) {
      resourcesByType[r.type] = []
    }
    resourcesByType[r.type].push(r)
  })

  const typeLabels: Record<string, string> = {
    model: '模型',
    python_package: 'Python 包',
    binary: '二进制',
  }

  const hasUnreadyResources = report.resources.some(r => r.status !== 'ready')

  return (
    <div className="settings-section">
      {/* 环境概览 */}
      <div className="settings-group">
        <h3 className="settings-group-title">环境概览</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: '8px 0' }}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Python</div>
          <div style={{ fontSize: 13 }}>{report.python_version}</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>GPU</div>
          <div style={{ fontSize: 13 }}>
            {report.gpu_available ? `${report.gpu_name} (CUDA ${report.cuda_version})` : '未检测到'}
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>总览</div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{report.summary}</div>
        </div>
      </div>

      {/* 资源列表 */}
      <div className="settings-group">
        <h3 className="settings-group-title">资源状态</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {Object.entries(typeLabels).map(([type, label]) => {
            const items = resourcesByType[type]
            if (!items || items.length === 0) return null

            return (
              <div key={type} style={{ marginBottom: 8 }}>
                <div style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                  marginBottom: 4,
                  marginTop: 4,
                }}>
                  {label}
                </div>
                {items.map(r => (
                  <ResourceItem key={r.id} resource={r} />
                ))}
              </div>
            )
          })}
        </div>
      </div>

      {/* 提示 */}
      {hasUnreadyResources && (
        <div className="settings-group">
          <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 0' }}>
            运行 <code style={{ background: 'var(--bg-secondary)', padding: '2px 6px', borderRadius: 4 }}>mbforge env setup</code> 自动搭建缺失资源。
            模型默认从 ModelScope 下载，Python 包使用清华源。
          </div>
        </div>
      )}
    </div>
  )
}
