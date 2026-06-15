// 存储管理栏目 — 缓存大小 + 清除按钮 + 模型迁移到统一缓存。

import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { invoke } from '@tauri-apps/api/core'
import SettingSection, { SettingGroup } from '../../ui/SettingSection'
import Button from '../../ui/Button'
import { showToast } from '../../../hooks/useToast'

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

interface ConsolidateResult {
  model_id: string
  from: string
  to: string
  files_copied: number
  already_present: boolean
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
  const [consolidating, setConsolidating] = useState(false)

  const refresh = useCallback(async () => {
    if (!projectRoot) return
    try {
      const s = await invoke<CacheSize>('cache_size', { projectRoot })
      setSize(s)
    } catch (e) {
      console.error('cache_size failed', e)
    }
  }, [projectRoot])

  useEffect(() => { void refresh() }, [refresh])

  const clear = async (kind: 'semantic' | 'detection' | 'molecules') => {
    setClearing(kind)
    try {
      const res = await invoke<ClearResult>('cache_clear', { projectRoot, cache: kind })
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

  const consolidate = async () => {
    setConsolidating(true)
    try {
      const results = await invoke<ConsolidateResult[]>('consolidate_models')
      const moved = results.filter(r => r.files_copied > 0).length
      const present = results.filter(r => r.already_present).length
      const none = results.filter(r => !r.already_present && r.files_copied === 0).length
      showToast(
        `迁移完成：${moved} 个模型已复制到统一缓存，${present} 个已就位，${none} 个未找到`,
        moved > 0 || present > 0 ? 'success' : 'info',
      )
    } catch (e) {
      showToast(String(e), 'error')
    } finally {
      setConsolidating(false)
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
            <div className="storage-row">
              <div className="storage-row-info">
                <span className="storage-row-label">{t('settings.consolidate')}</span>
                <span className="storage-row-size">{t('settings.consolidateDesc')}</span>
              </div>
              <Button
                size="sm"
                variant="secondary"
                disabled={consolidating}
                onClick={consolidate}
              >
                {consolidating ? t('settings.consolidating') : t('settings.consolidate')}
              </Button>
            </div>
          </div>
        )}
      </SettingGroup>
    </SettingSection>
  )
}
