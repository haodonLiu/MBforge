// 设置面板 — 主协调器。
//
// 结构：左侧 7 个顶级栏目导航 + 右侧当前栏目的内容。
// 每个栏目的实现都在 `components/settings/sections/` 下独立文件，
// 共享同一个 `SettingsState`（在 `types.ts` 里定义）。
//
// 关键不变量：
// 1. 所有 section 都接收 `(settings, setSettings)`，共享一份状态。
// 2. 保存时通过 `toBackendPayload` 把扁平 state 拍平为后端 JSON。
// 3. 加载时通过 `flattenSettings` 把后端 JSON 拍平回 state。
// 4. 脏状态用 `isSettingsEqual` 浅比较，不用 JSON.stringify。

import { useState, useEffect, useCallback, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { ask } from '@tauri-apps/plugin-dialog'
import i18n from '../i18n'
import {
  SettingsIcon, XIcon, DownloadIcon, CpuIcon,
  LayoutIcon, FlaskIcon, InfoIcon,
} from './icons'
import { getSettings, saveSettings, getConfigDir } from '../api/settings'
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
import AboutSection from './settings/sections/AboutSection'

// ============ Section Icon Map ============
const SECTION_ICONS: Record<SectionDef['icon'], ReactNode> = {
  settings: <SettingsIcon size={18} />,
  download: <DownloadIcon size={18} />,
  cpu: <CpuIcon size={18} />,
  flask: <FlaskIcon size={18} />,
  info: <InfoIcon size={18} />,
  layout: <LayoutIcon size={18} />,
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function SettingsModal({ open, onClose }: Props) {
  const [activeSection, setActiveSection] = useState<SectionId>('general')
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS)
  const [initialSettings, setInitialSettings] = useState<SettingsState>(DEFAULT_SETTINGS)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [saveSuccess, setSaveSuccess] = useState(false)

  const { t } = useTranslation()
  const { setTheme } = useTheme()

  // 脏状态 — 浅比较，避免 JSON.stringify 引入的误报
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
        // 局部副作用：保存后立即应用主题/语言。
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

  // 加载
  useEffect(() => {
    if (open) {
      void loadSettings()
    }
  }, [open, loadSettings])

  // 各 section 渲染
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
      case 'about':
        return (
          <AboutSection
            onReset={handleReset}
            onOpenConfig={handleOpenConfigDir}
          />
        )
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
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <motion.div
          onClick={confirmClose}
          variants={fadeIn}
          initial="hidden"
          animate="visible"
          exit="hidden"
          style={{
            position: 'absolute',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.45)',
            backdropFilter: 'blur(8px)',
            WebkitBackdropFilter: 'blur(8px)',
          }}
        />
        <motion.div
          variants={modalEntrance}
          initial="hidden"
          animate="visible"
          exit="exit"
          style={{
            position: 'relative',
            width: '90%',
            maxWidth: '860px',
            height: '80%',
            maxHeight: '640px',
            background: 'var(--bg-surface)',
            borderRadius: '16px',
            border: '1px solid var(--border)',
            boxShadow: '0 20px 60px rgba(0, 0, 0, 0.3)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 20px',
            borderBottom: '1px solid var(--border)',
          }}>
            <h2 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>{t('settings.title')}</h2>
            <IconButton size={32} onClick={confirmClose} title={t('common.close')}>
              <XIcon size={18} />
            </IconButton>
          </div>

          {/* Content */}
          <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
            {/* Left nav */}
            <div style={{
              width: '180px',
              borderRight: '1px solid var(--border)',
              padding: '12px 8px',
              overflowY: 'auto',
            }}>
              {SECTIONS.map(section => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    border: 'none',
                    background: activeSection === section.id ? 'var(--accent-muted)' : 'transparent',
                    color: activeSection === section.id ? 'var(--accent)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                    fontSize: '13px',
                    textAlign: 'left',
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => {
                    if (activeSection !== section.id) e.currentTarget.style.background = 'var(--bg-hover)'
                  }}
                  onMouseLeave={e => {
                    if (activeSection !== section.id) e.currentTarget.style.background = 'transparent'
                  }}
                >
                  {SECTION_ICONS[section.icon]}
                  <span>{t(section.labelKey)}</span>
                </button>
              ))}
            </div>

            {/* Right content */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
                <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>
                  {sectionData ? t(sectionData.labelKey) : ''}
                </h3>
              </div>

              <ScrollColumn padding="16px 20px">
                {error && <AlertBanner variant="danger" message={error} onDismiss={() => setError('')} />}
                {saveSuccess && <AlertBanner variant="success" message={t('settings.saved')} />}
                <ErrorBoundary key={activeSection} onError={() => showToast(t('error.title'), 'error')}>
                  <div>
                    {renderSection()}
                  </div>
                </ErrorBoundary>
              </ScrollColumn>

              {/* Footer */}
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '12px 20px',
                borderTop: '1px solid var(--border)',
              }}>
                <span style={{ fontSize: 11, color: isDirty ? 'var(--accent)' : 'var(--text-muted)' }}>
                  {isDirty ? '● ' + t('settings.unsavedChangesTitle') : ''}
                </span>
                <div style={{ display: 'flex', gap: 8 }}>
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