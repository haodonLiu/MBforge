/** Per-PDF molecule detection cache stats + clear button.
 * Used by Settings > System tab. */

import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getDetectionCacheStats, clearDetectionCache } from '../../api/tauri'
import { useAppContext } from '../../context/AppContext'
import { showToast } from '../../hooks/useToast'
import Button from '../ui/Button'
import Caption from '../ui/Caption'

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

export default function DetectionCacheCard() {
  const { t } = useTranslation()
  const { projectRoot } = useAppContext()
  const [stats, setStats] = useState<{
    disk_usage_bytes: number
    cached_page_count: number
    cached_doc_count: number
    schema_version: number
  } | null>(null)
  const [loading, setLoading] = useState(false)
  const [clearing, setClearing] = useState(false)

  const refresh = useCallback(async () => {
    if (!projectRoot) {
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
      showToast(t('settings.cacheCleared'), 'success')
      await refresh()
    } catch (e) {
      showToast(t('settings.cacheClearFailed') + ': ' + (e instanceof Error ? e.message : String(e)), 'error')
    } finally {
      setClearing(false)
    }
  }

  return (
    <div
      style={{
        padding: '14px 18px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>{t('settings.cacheDetectionTitle')}</h3>
        <Button variant="secondary" size="sm" onClick={refresh} disabled={loading}>
          {loading ? t('common.loading') : t('common.refresh')}
        </Button>
      </div>
      <Caption>
        {t('settings.cacheDetectionDesc')}
      </Caption>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: '10px',
        }}
      >
        <Stat label={t('settings.cacheDiskUsage')} value={stats ? formatBytes(stats.disk_usage_bytes) : '—'} />
        <Stat label={t('settings.cachePageCount')} value={stats ? String(stats.cached_page_count) : '—'} />
        <Stat label={t('settings.cacheDocCount')} value={stats ? String(stats.cached_doc_count) : '—'} />
        <Stat label="Schema" value={stats ? `v${stats.schema_version}` : '—'} />
      </div>
      <div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleClear}
          loading={clearing}
          disabled={!stats || stats.cached_page_count === 0}
        >
          {t('settings.cacheClearDetection')}
        </Button>
      </div>
    </div>
  )
}

interface StatProps {
  label: string
  value: string
}

function Stat({ label, value }: StatProps) {
  return (
    <div
      style={{
        padding: '8px 10px',
        background: 'var(--bg-base)',
        border: '1px solid var(--border)',
        borderRadius: '6px',
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      <Caption style={{ fontSize: 11 }}>{label}</Caption>
      <span style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'ui-monospace, monospace' }}>
        {value}
      </span>
    </div>
  )
}
