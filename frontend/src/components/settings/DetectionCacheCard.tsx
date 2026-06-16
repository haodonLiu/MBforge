/** Per-PDF molecule detection cache stats + clear button.
 * Used by Settings > System tab. */

import { useCallback, useEffect, useState } from 'react'
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
      showToast('检测缓存已清空', 'success')
      await refresh()
    } catch (e) {
      showToast('清空失败: ' + (e instanceof Error ? e.message : String(e)), 'error')
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
        <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>分子检测缓存</h3>
        <Button variant="secondary" size="sm" onClick={refresh} disabled={loading}>
          {loading ? '刷新中…' : '刷新'}
        </Button>
      </div>
      <Caption>
        缓存每页 PDF 的分子检测结果，再次打开同一页时直接读盘，跳过模型推理。
      </Caption>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: '10px',
        }}
      >
        <Stat label="磁盘占用" value={stats ? formatBytes(stats.disk_usage_bytes) : '—'} />
        <Stat label="已缓存页数" value={stats ? String(stats.cached_page_count) : '—'} />
        <Stat label="已缓存文档数" value={stats ? String(stats.cached_doc_count) : '—'} />
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
          清空所有检测缓存
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
