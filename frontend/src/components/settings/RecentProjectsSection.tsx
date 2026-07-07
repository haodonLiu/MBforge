// 最近项目栏目 — 从 AppConfig.recent_projects 读，列表 + 打开/移除/清空。

import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { httpGet, httpPut } from '../../api/http/_utils'
import SettingSection, { SettingGroup } from '@/components/ui/SettingSection'
import Button from '@/components/ui/Button'
import { showToast } from '../../hooks/useToast'
import { openProject } from '../../api/http/project'

export default function RecentProjectsSection() {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<string[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await httpGet<{ settings?: { recent_projects?: string[] } }>('/api/v1/settings')
      setProjects(resp.settings?.recent_projects ?? [])
    } catch (e) {
      console.error('load recent projects failed', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const onOpen = async (path: string) => {
    try {
      const resp = await openProject(path)
      if (resp.success) {
        const current = await httpGet<{ settings?: { recent_projects?: string[] } }>('/api/v1/settings')
        const recent = current.settings?.recent_projects ?? []
        if (!recent.includes(path)) {
          await httpPut('/api/v1/settings', { recent_projects: [path, ...recent].slice(0, 20) })
        }
        showToast(t('settings.recentOpen') + ' ✓', 'success')
      } else {
        showToast(resp.error || t('settings.recentOpen') + ' ✗', 'error')
      }
    } catch (e) {
      showToast(String(e), 'error')
    }
  }

  const onRemove = async (path: string) => {
    try {
      const current = await httpGet<{ settings?: { recent_projects?: string[] } }>('/api/v1/settings')
      const recent = (current.settings?.recent_projects ?? []).filter((p: string) => p !== path)
      await httpPut('/api/v1/settings', { recent_projects: recent })
      setProjects(recent)
    } catch (e) {
      showToast(String(e), 'error')
    }
  }

  const onClear = async () => {
    try {
      await httpPut('/api/v1/settings', { recent_projects: [] })
      setProjects([])
    } catch (e) {
      showToast(String(e), 'error')
    }
  }

  return (
    <SettingSection>
      <SettingGroup title={t('settings.recentProjects')}>
        {loading ? (
          <div className="settings-empty-state">…</div>
        ) : projects.length === 0 ? (
          <div className="settings-empty-state">{t('settings.recentProjectsEmpty')}</div>
        ) : (
          <div className="recent-projects-list">
            {projects.map(p => (
              <div key={p} className="recent-projects-row">
                <code className="recent-projects-path" title={p}>{p}</code>
                <div className="recent-projects-actions">
                  <Button size="sm" variant="primary" onClick={() => onOpen(p)}>
                    {t('settings.recentOpen')}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => onRemove(p)}>
                    {t('settings.recentRemove')}
                  </Button>
                </div>
              </div>
            ))}
            <div className="recent-projects-footer">
              <Button size="sm" variant="ghost" onClick={onClear}>
                {t('settings.recentClear')}
              </Button>
            </div>
          </div>
        )}
      </SettingGroup>
    </SettingSection>
  )
}
