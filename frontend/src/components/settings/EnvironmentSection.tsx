import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { resourcesCheck, type EnvironmentReport } from '../../api/tauri-bridge'
import Spinner from '../ui/Spinner'
import Caption from '../ui/Caption'
import Badge from '../ui/Badge'

interface ResourceItem {
  id: string
  name: string
  type: string
  status: string
  version?: string
  local_path?: string
  size_mb: number
}

function ResourceItem({ resource }: { resource: ResourceItem }) {
  const { t } = useTranslation()
  const statusLabel = resource.status === 'ready'
    ? t('env.ready')
    : resource.status === 'not_found'
      ? t('env.notDownloaded')
      : resource.status

  return (
    <div className="resource-item">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
        <span style={{ fontSize: '13px', fontWeight: 500 }}>{resource.name}</span>
        {resource.local_path && (
          <Caption style={{ fontFamily: 'monospace', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {resource.local_path}
          </Caption>
        )}
        {resource.version && (
          <Caption>v{resource.version}</Caption>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {resource.size_mb > 0 && (
          <Caption>{resource.size_mb} MB</Caption>
        )}
        <Badge variant={resource.status === 'ready' ? 'success' : 'warning'} style={{ fontWeight: 600 }}>
          {statusLabel}
        </Badge>
      </div>
    </div>
  )
}

export default function EnvironmentSection() {
  const { t } = useTranslation()
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
      <div className="settings-section" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px' }}>
        <Spinner size={20} />
        <Caption style={{ marginLeft: '12px' }}>{t('env.checking')}</Caption>
      </div>
    )
  }

  if (!report || !report.resources) {
    return (
      <div className="settings-section">
        <Caption color="var(--danger)">{t('env.cannotGetInfo')}</Caption>
      </div>
    )
  }

  const resourcesByType: Record<string, ResourceItem[]> = {}
  report.resources.forEach(r => {
    if (!resourcesByType[r.type]) resourcesByType[r.type] = []
    resourcesByType[r.type].push(r)
  })

  const typeLabels: Record<string, string> = {
    model: t('env.models'),
    python_package: t('env.pythonPackages'),
    binary: t('env.binaries'),
  }

  const hasUnreadyResources = report.resources.some(r => r.status !== 'ready')

  return (
    <div className="settings-section">
      <div className="settings-group">
        <h3 className="settings-group-title">{t('env.overview')}</h3>
        <div className="env-overview-grid">
          <Caption>{t('env.python')}</Caption>
          <span style={{ fontSize: '13px' }}>{report.python_version}</span>
          <Caption>GPU</Caption>
          <span style={{ fontSize: '13px' }}>
            {report.gpu_available ? `${report.gpu_name} (CUDA ${report.cuda_version})` : t('env.notDetected')}
          </span>
          <Caption>{t('env.summary')}</Caption>
          <span style={{ fontSize: '13px', fontWeight: 600 }}>{report.summary}</span>
        </div>
      </div>

      <div className="settings-group">
        <h3 className="settings-group-title">{t('env.resourceStatus')}</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {Object.entries(typeLabels).map(([type, label]) => {
            const items = resourcesByType[type]
            if (!items || items.length === 0) return null
            return (
              <div key={type} style={{ marginBottom: '8px' }}>
                <div className="resource-type-label">{label}</div>
                {items.map(r => (
                  <ResourceItem key={r.id} resource={r} />
                ))}
              </div>
            )
          })}
        </div>
      </div>

      {hasUnreadyResources && (
        <div className="settings-group">
          <Caption style={{ padding: '8px 0' }}>
            {t('env.runSetup')} <code className="inline-code">mbforge env setup</code> {t('env.autoSetupHint')}
          </Caption>
        </div>
      )}
    </div>
  )
}
