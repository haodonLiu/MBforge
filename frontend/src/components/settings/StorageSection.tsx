// 存储管理栏目 — 缓存大小 + 清除按钮。

import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { httpPost } from '../../api/http/_utils'
import SettingSection, { SettingGroup } from '@/components/ui/SettingSection'
import Button from '@/components/ui/Button'
import { showToast } from '../../hooks/useToast'

interface CacheSize {
  semantic_mb: number
  detection_mb: number
  molecules_mb: number
}

interface ClearResult {
  cache: string
  freed_mb: number
  success: boolean
  error: string
}

interface Props {
  projectRoot: string
}

function fmtSize(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`
  if (mb >= 1) return `${mb.toFixed(1)} MB`
  if (mb > 0) return `${(mb * 1024).toFixed(0)} KB`
  return '0'
}

export default function StorageSection({ projectRoot }: Props) {
  const { t } = useTranslation()
  const [size, setSize] = useState<CacheSize | null>(null)
  const [clearing, setClearing] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!projectRoot) return
    try {
      const s = await httpPost<CacheSize>('/api/v1/settings/cache-size', { project_root: projectRoot })
      setSize(s)
    } catch (e) {
      console.error('cache_size failed', e)
    }
  }, [projectRoot])

  useEffect(() => { void refresh() }, [refresh])

  const clear = async (kind: 'semantic' | 'detection' | 'molecules') => {
    setClearing(kind)
    try {
      const res = await httpPost<ClearResult>('/api/v1/settings/cache-clear', { project_root: projectRoot, cache: kind })
      if (res.success) {
        showToast(`已释放 ${fmtSize(res.freed_mb)}`, 'success')
        void refresh()
      } else {
        showToast(res.error || '清除失败', 'error')
      }
    } catch (e) {
      showToast(String(e), 'error')
    } finally {
      setClearing(null)
    }
  }

  if (!projectRoot) {
    return (
      <SettingSection>
        <SettingGroup title={t('settings.cache')}>
          <div className="settings-empty-state">
            {t('settings.activeProject') + ': —'}
          </div>
        </SettingGroup>
      </SettingSection>
    )
  }

  const rows: Array<{ key: 'semantic' | 'detection' | 'molecules'; label: string; mb: number }> = size
    ? [
        { key: 'semantic', label: t('settings.cacheSemantic'), mb: size.semantic_mb },
        { key: 'detection', label: t('settings.cacheDetection'), mb: size.detection_mb },
        { key: 'molecules', label: t('settings.cacheMolecules'), mb: size.molecules_mb },
      ]
    : []

  return (
    <SettingSection>
      <SettingGroup title={t('settings.cache')}>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px' }}>
          {t('settings.cacheDesc')}
        </div>
        {!size ? (
          <div className="settings-empty-state">…</div>
        ) : (
          <div className="storage-list">
            {rows.map(row => (
              <div key={row.key} className="storage-row">
                <div className="storage-row-info">
                  <span className="storage-row-label">{row.label}</span>
                  <span className="storage-row-size">{fmtSize(row.mb)}</span>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={row.mb === 0 || clearing !== null}
                  onClick={() => void clear(row.key)}
                >
                  {clearing === row.key ? t('settings.cacheClearing') : t('settings.cacheClear')}
                </Button>
              </div>
            ))}
          </div>
        )}
      </SettingGroup>
    </SettingSection>
  )
}
