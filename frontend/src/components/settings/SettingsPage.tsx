import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useAppContext } from '@/context/AppContext'
import PageContainer from '@/components/ui/PageContainer'
import PageTitle from '@/components/ui/PageTitle'
import AlertBanner from '@/components/ui/AlertBanner'
import Button from '@/components/ui/Button'
import SettingsTabs from '@/components/settings/SettingsTabs'
import { getSettings, saveSettings, getConfigDir } from '@/api/http/settings'
import { useTheme } from '@/hooks/useTheme'
import i18n from '@/i18n'
import { showToast } from '@/hooks/useToast'
import {
  DEFAULT_SETTINGS,
  flattenSettings,
  toBackendPayload,
  isSettingsEqual,
  type SettingsState,
} from '@/components/settings/types'

export default function SettingsPage() {
  const { t } = useTranslation()
  const { projectRoot } = useAppContext()
  const { setTheme } = useTheme()

  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS)
  const [initialSettings, setInitialSettings] = useState<SettingsState>(DEFAULT_SETTINGS)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [buttonSaved, setButtonSaved] = useState(false)
  const [saveErrorShake, setSaveErrorShake] = useState(false)

  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  const isDirty = !isSettingsEqual(settings, initialSettings)

  const loadSettings = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      const resp = await getSettings()
      if (resp.success && resp.settings) {
        const loaded = flattenSettings(resp.settings)
        setSettings(loaded)
        setInitialSettings(loaded)
      } else {
        const msg = resp.error || t('settings.loadFailed')
        setError(msg)
      }
    } catch (e) {
      const msg = t('settings.loadFailed') + ': ' + (e instanceof Error ? e.message : String(e))
      setError(msg)
      showToast(msg, 'error')
    } finally {
      setIsLoading(false)
    }
  }, [t])

  const handleSave = useCallback(async () => {
    setIsLoading(true)
    setError('')
    setSaveSuccess(false)
    try {
      const payload = toBackendPayload(settings)
      const resp = await saveSettings(payload)
      if (resp.success) {
        setSaveSuccess(true)
        setButtonSaved(true)
        setInitialSettings(settings)
        const effectiveTheme = settings.theme === 'system' ? 'dark' : settings.theme
        setTheme(effectiveTheme)
        void i18n.changeLanguage(settings.language)
        timersRef.current.push(setTimeout(() => setSaveSuccess(false), 3000))
        timersRef.current.push(setTimeout(() => setButtonSaved(false), 1500))
      } else {
        const msg = resp.error || t('settings.saveFailed')
        setError(msg)
        setSaveErrorShake(true)
        showToast(msg, 'error')
        timersRef.current.push(setTimeout(() => setSaveErrorShake(false), 300))
      }
    } catch (e) {
      const msg = t('settings.saveFailed') + ': ' + (e instanceof Error ? e.message : String(e))
      setError(msg)
      setSaveErrorShake(true)
      showToast(msg, 'error')
      timersRef.current.push(setTimeout(() => setSaveErrorShake(false), 300))
    } finally {
      setIsLoading(false)
    }
  }, [settings, t, setTheme])

  const handleReset = useCallback(() => {
    setSettings(DEFAULT_SETTINGS)
    showToast(t('settings.resetHint'), 'info')
  }, [t])

  const handleOpenConfigDir = useCallback(async () => {
    try {
      const path = await getConfigDir()
      showToast(path, 'info')
    } catch (e) {
      showToast(String(e), 'error')
    }
  }, [])

  useEffect(() => {
    void loadSettings()
  }, [loadSettings])

  useEffect(() => {
    return () => {
      timersRef.current.forEach(clearTimeout)
      timersRef.current = []
    }
  }, [])

  return (
    <PageContainer>
      <div className="settings-page-header">
        <PageTitle>{t('settings.title')}</PageTitle>
        <div className="settings-page-actions">
          <span
            className={`settings-unsaved-indicator ${isDirty ? 'settings-unsaved-indicator--visible' : 'settings-unsaved-indicator--hidden'}`}
          >
            {isDirty ? '● ' + t('settings.unsavedChangesTitle') : ''}
          </span>
          <Button variant="secondary" onClick={loadSettings} disabled={isLoading}>
            {t('common.cancel')}
          </Button>
          <Button
            variant={buttonSaved ? 'success' : 'primary'}
            onClick={handleSave}
            disabled={isLoading || !isDirty}
            loading={isLoading}
            className={saveErrorShake ? 'settings-save-button--error' : undefined}
          >
            {isLoading ? t('settings.saving') : buttonSaved ? t('settings.saved') + ' ✓' : t('common.save')}
          </Button>
        </div>
      </div>

      {error && (
        <AlertBanner
          variant="danger"
          message={error}
          onDismiss={() => setError('')}
          className="settings-alert"
        />
      )}
      {saveSuccess && (
        <AlertBanner
          variant="success"
          message={t('settings.saved')}
          className="settings-alert"
        />
      )}

      <SettingsTabs
        settings={settings}
        setSettings={setSettings}
        projectRoot={projectRoot}
        onReset={handleReset}
        onOpenConfig={handleOpenConfigDir}
      />
    </PageContainer>
  )
}
