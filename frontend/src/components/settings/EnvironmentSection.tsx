import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  resourcesCheck, type EnvironmentReport,
  getDetectionCacheStats, clearDetectionCache,
  type DetectionCacheStats,
} from '../../api/tauri-bridge'
import { isTauriAvailable } from '../../api/tauri/_utils'
import { useAppContext } from '../../context/AppContext'
import { showToast } from '../../hooks/useToast'
import Spinner from '../ui/Spinner'
import Caption from '../ui/Caption'
import Badge from '../ui/Badge'
import Button from '../ui/Button'

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
  const [statusFilter, setStatusFilter] = useState<'all' | 'ready' | 'not_ready'>('all')

  useEffect(() => {
    setLoading(true)
    // 在 Tauri 外部（浏览器开发模式）不调用 IPC，避免抛错造成页面崩溃。
    if (!isTauriAvailable()) {
      setReport(null)
      setLoading(false)
      return
    }
    let cancelled = false
    resourcesCheck()
      .then(r => { if (!cancelled) setReport(r) })
      .catch(() => { if (!cancelled) setReport(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
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
  report.resources
    .filter(r => statusFilter === 'all' || r.status === statusFilter)
    .forEach(r => {
      if (!resourcesByType[r.type]) resourcesByType[r.type] = []
      resourcesByType[r.type].push(r)
    })

  const typeLabels: Record<string, string> = {
    model: t('env.models'),
    python_package: t('env.pythonPackages'),
    binary: t('env.binaries'),
  }

  const hasUnreadyResources = report.resources.some(r => r.status !== 'ready')
  const counts = {
    all: report.resources.length,
    ready: report.resources.filter(r => r.status === 'ready').length,
    not_ready: report.resources.filter(r => r.status !== 'ready').length,
  }

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
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <h3 className="settings-group-title" style={{ margin: 0 }}>{t('env.resourceStatus')}</h3>
          <div style={{ display: 'flex', gap: '4px' }}>
            <FilterPill active={statusFilter === 'all'} onClick={() => setStatusFilter('all')}>
              {t('env.filterAll')} ({counts.all})
            </FilterPill>
            <FilterPill active={statusFilter === 'ready'} onClick={() => setStatusFilter('ready')}>
              {t('env.filterReady')} ({counts.ready})
            </FilterPill>
            <FilterPill active={statusFilter === 'not_ready'} onClick={() => setStatusFilter('not_ready')}>
              {t('env.filterNotReady')} ({counts.not_ready})
            </FilterPill>
          </div>
        </div>
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

      <DetectionCacheCard />
    </div>
  )
}

/** Per-PDF molecule detection cache stats + clear button. */
function DetectionCacheCard() {
  const { projectRoot } = useAppContext()
  const [stats, setStats] = useState<DetectionCacheStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [clearing, setClearing] = useState(false)

  const refresh = useCallback(async () => {
    if (!projectRoot || !isTauriAvailable()) {
      setStats(null)
      return
    }
    setLoading(true)
    try {
      const s = await getDetectionCacheStats(projectRoot)
      setStats(s)
    } catch (e) {
      console.warn('[DetectionCacheCard] stats failed:', e)
      setStats(null)
    } finally {
      setLoading(false)
    }
  }, [projectRoot])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const handleClear = async () => {
    if (!projectRoot) return
    setClearing(true)
    try {
      await clearDetectionCache(projectRoot)
      showToast('检测缓存已清空', 'success')
      await refresh()
    } catch (e) {
      showToast('清空失败: ' + (e instanceof Error ? e.message : String(e)), 'error')
    } finally {
      setClearing(false)
    }
  }

  const formatBytes = (n: number) => {
    if (n < 1024) return `${n} B`
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
    return `${(n / 1024 / 1024).toFixed(2)} MB`
  }

  return (
    <div className="settings-group">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
        <h3 className="settings-group-title" style={{ margin: 0 }}>分子检测缓存</h3>
        <Button variant="secondary" size="sm" onClick={refresh} disabled={loading}>
          {loading ? '刷新中…' : '刷新'}
        </Button>
      </div>
      <Caption style={{ marginBottom: '8px' }}>
        缓存每页 PDF 的分子检测结果，再次打开同一页时直接读盘，跳过模型推理。
      </Caption>
      <div className="env-overview-grid">
        <Caption>磁盘占用</Caption>
        <span style={{ fontSize: '13px', fontFamily: 'monospace' }}>
          {stats ? formatBytes(stats.disk_usage_bytes) : '—'}
        </span>
        <Caption>已缓存页数</Caption>
        <span style={{ fontSize: '13px', fontFamily: 'monospace' }}>
          {stats ? stats.cached_page_count : '—'}
        </span>
        <Caption>已缓存文档数</Caption>
        <span style={{ fontSize: '13px', fontFamily: 'monospace' }}>
          {stats ? stats.cached_doc_count : '—'}
        </span>
        <Caption>Schema 版本</Caption>
        <span style={{ fontSize: '13px', fontFamily: 'monospace' }}>
          {stats ? `v${stats.schema_version}` : '—'}
        </span>
      </div>
      <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleClear}
          loading={clearing}
          disabled={!stats || stats.cached_page_count === 0}
        >
          清空所有检测缓存
        </Button>
      </div>
    </div>
  )
}

function FilterPill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '2px 10px',
        background: active ? 'var(--accent-muted)' : 'var(--bg-elevated)',
        color: active ? 'var(--accent)' : 'var(--text-secondary)',
        border: 'none',
        borderRadius: 12,
        cursor: 'pointer',
        fontSize: 11,
        fontWeight: 500,
        transition: 'all 0.1s',
      }}
    >
      {children}
    </button>
  )
}
