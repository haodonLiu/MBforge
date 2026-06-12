// 最近项目栏目 — 从 AppConfig.recent_projects 读，列表 + 打开/移除/清空。

import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { invoke } from '@tauri-apps/api/core'
import SettingSection, { SettingGroup } from '../../ui/SettingSection'
import Button from '../../ui/Button'
import { showToast } from '../../../hooks/useToast'
import { openProject } from '../../../api/tauri/project'

export default function RecentProjectsSection() {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<string[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await invoke<{ projects: string[] }>('projects_list_recent')
      setProjects(resp.projects)
    } catch (e) {
      console.error('projects_list_recent failed', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const onOpen = async (path: string) => {
    try {
      const resp = await openProject(path)
      if (resp.success) {
        // openProject 内部会写 recent，但保险起见手动加一次
        await invoke('projects_add_recent', { path })
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
      const resp = await invoke<{ projects: string[] }>('projects_remove_recent', { path })
      setProjects(resp.projects)
    } catch (e) {
      showToast(String(e), 'error')
    }
  }

  const onClear = async () => {
    try {
      const resp = await invoke<{ projects: string[] }>('projects_clear_recent')
      setProjects(resp.projects)
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
