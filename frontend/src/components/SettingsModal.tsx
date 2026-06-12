// 设置面板 — 主协调器。
//
// 结构：左侧 7 个顶级栏目导航 + 右侧当前栏目的内容。
// 每个栏目的实现都在 `components/settings/sections/` 下独立文件，
// 共享同一个 `SettingsState`（在 `types.ts` 里定义）。

import { useState, useEffect, useCallback, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { invoke } from '@tauri-apps/api/core'
import { useTranslation } from 'react-i18next'
import { ask } from '@tauri-apps/plugin-dialog'
import i18n from '../i18n'
import {
  SettingsIcon, XIcon, DownloadIcon, CpuIcon,
  LayoutIcon, FlaskIcon, InfoIcon, FolderOpenIcon, RefreshCwIcon,
} from './icons'
import { getSettings, saveSettings, getConfigDir } from '../api/tauri/settings'
import { useTheme } from '../hooks/useTheme'
import { fadeIn, modalEntrance } from '../hooks/useAnimations'
import AlertBanner from './ui/AlertBanner'
import Button from './ui/Button'
import IconButton from './ui/IconButton'
import { ScrollColumn } from './ui'
import ErrorBoundary from './ErrorBoundary'
import { showToast } from '../hooks/useToast'

import {
  SECTIONS, type SectionId, type SectionDef,
  DEFAULT_SETTINGS, flattenSettings, toBackendPayload, isSettingsEqual,
  type SettingsState,
} from './settings/types'

import GeneralSection from './settings/sections/GeneralSection'
import AIModelsSection from './settings/sections/AIModelsSection'
import ModelServiceSection from './settings/sections/ModelServiceSection'
import ModelDownloadsSection from './settings/sections/ModelDownloadsSection'
import PdfParseSection from './settings/sections/PdfParseSection'
import StorageSection from './settings/sections/StorageSection'
import RecentProjectsSection from './settings/sections/RecentProjectsSection'
import AboutSection from './settings/sections/AboutSection'

const SECTION_ICONS: Record<SectionDef['icon'], ReactNode> = {
  settings: <SettingsIcon size={18} />,
  download: <DownloadIcon size={18} />,
  cpu: <CpuIcon size={18} />,
  flask: <FlaskIcon size={18} />,
  info: <InfoIcon size={18} />,
  layout: <LayoutIcon size={18} />,
  folder: <FolderOpenIcon size={18} />,
  refresh: <RefreshCwIcon size={18} />,
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function SettingsModal({ open, onClose }: Props) {
  const [activeSection, setActiveSection] = useState<SectionId>('general')
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS)
  const [initialSettings, setInitialSettings] = useState<SettingsState>(DEFAULT_SETTINGS)
  const [activeProject, setActiveProject] = useState<string>('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [saveSuccess, setSaveSuccess] = useState(false)

  const { t } = useTranslation()
  const { setTheme } = useTheme()

  const isDirty = !isSettingsEqual(settings, initialSettings)

  const confirmClose = useCallback(async () => {
    if (isDirty) {
      const ok = await ask(t('settings.unsavedChanges'), {
        title: t('settings.unsavedChangesTitle') || t('settings.unsavedChanges'),
        kind: 'warning',
      })
      if (!ok) return
    }
    onClose()
  }, [isDirty, onClose, t])

  const loadSettings = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      const resp = await getSettings()
      if (resp.success && resp.settings) {
        const loaded = flattenSettings(resp.settings)
        setSettings(loaded)
        setInitialSettings(loaded)
      }
      // 取最近项目列表的首项作为"当前项目"代理（用于缓存管理）
      try {
        const recent = await invoke<{ projects: string[] }>('projects_list_recent')
        setActiveProject(recent.projects[0] ?? '')
      } catch { /* 静默 */ }
    } catch (e) {
      showToast('加载设置失败: ' + (e instanceof Error ? e.message : String(e)), 'error')
    } finally {
      setIsLoading(false)
    }
  }, [])

  const handleSave = async () => {
    setIsLoading(true)
    setError('')
    setSaveSuccess(false)
    try {
      const payload = toBackendPayload(settings)
      const resp = await saveSettings(payload)
      if (resp.success) {
        setSaveSuccess(true)
        setInitialSettings(settings)
        setTheme(settings.theme === 'system' ? 'dark' : settings.theme)
        void i18n.changeLanguage(settings.language)
        setTimeout(() => setSaveSuccess(false), 3000)
      } else {
        const msg = resp.error || t('settings.saveFailed')
        setError(msg)
        showToast(msg, 'error')
      }
    } catch (e) {
      setError(t('settings.saveFailed'))
      showToast(t('settings.saveFailed') + ': ' + (e instanceof Error ? e.message : String(e)), 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleReset = () => {
    setSettings(DEFAULT_SETTINGS)
    showToast(t('settings.resetHint'), 'info')
  }

  const handleOpenConfigDir = async () => {
    try {
      const path = await getConfigDir()
      showToast(path, 'info')
    } catch (e) {
      showToast(String(e), 'error')
    }
  }

  useEffect(() => {
    if (open) void loadSettings()
  }, [open, loadSettings])

  const renderSection = () => {
    switch (activeSection) {
      case 'general':
        return <GeneralSection settings={settings} setSettings={setSettings} />
      case 'ai_models':
        return <AIModelsSection settings={settings} setSettings={setSettings} />
      case 'model_service':
        return <ModelServiceSection settings={settings} setSettings={setSettings} />
      case 'model_downloads':
        return <ModelDownloadsSection settings={settings} setSettings={setSettings} />
      case 'pdf_parse':
        return <PdfParseSection settings={settings} setSettings={setSettings} />
      case 'storage':
        return <StorageSection projectRoot={activeProject} />
      case 'recent_projects':
        return <RecentProjectsSection />
      case 'about':
        return <AboutSection onReset={handleReset} onOpenConfig={handleOpenConfigDir} />
      default:
        return null
    }
  }

  if (!open) return null
  const sectionData = SECTIONS.find(s => s.id === activeSection)

  return (
    <AnimatePresence>
      <motion.div
        variants={fadeIn}
        initial="hidden"
        animate="visible"
        exit="hidden"
        className="settings-modal-overlay"
      >
        <motion.div
          onClick={confirmClose}
          variants={fadeIn}
          initial="hidden"
          animate="visible"
          exit="hidden"
          className="settings-modal-backdrop"
        />
        <motion.div
          variants={modalEntrance}
          initial="hidden"
          animate="visible"
          exit="exit"
          className="settings-modal"
        >
          <div className="settings-modal-header">
            <h2 className="settings-modal-title">{t('settings.title')}</h2>
            <IconButton size={32} onClick={confirmClose} title={t('common.close')}>
              <XIcon size={18} />
            </IconButton>
          </div>

          <div className="settings-modal-body">
            <div className="settings-modal-nav">
              {SECTIONS.map(section => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={`settings-nav-item ${activeSection === section.id ? 'settings-nav-item--active' : ''}`}
                >
                  {SECTION_ICONS[section.icon]}
                  <span>{t(section.labelKey)}</span>
                </button>
              ))}
            </div>

            <div className="settings-modal-content">
              <div className="settings-modal-section-header">
                <h3 className="settings-modal-section-title">
                  {sectionData ? t(sectionData.labelKey) : ''}
                </h3>
              </div>

              <ScrollColumn padding="16px 20px">
                {error && <AlertBanner variant="danger" message={error} onDismiss={() => setError('')} />}
                {saveSuccess && <AlertBanner variant="success" message={t('settings.saved')} />}
                <ErrorBoundary key={activeSection} onError={() => showToast(t('error.title'), 'error')}>
                  <div>{renderSection()}</div>
                </ErrorBoundary>
              </ScrollColumn>

              <div className="settings-modal-footer">
                <span className={`settings-modal-dirty ${isDirty ? 'settings-modal-dirty--active' : ''}`}>
                  {isDirty ? '● ' + t('settings.unsavedChangesTitle') : ''}
                </span>
                <div className="settings-modal-actions">
                  <Button variant="secondary" onClick={loadSettings} disabled={isLoading}>
                    {t('common.cancel')}
                  </Button>
                  <Button variant="primary" onClick={handleSave} disabled={isLoading} loading={isLoading}>
                    {isLoading ? t('settings.saving') : t('common.save')}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
