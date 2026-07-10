import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import Tabs from '@/components/ui/Tabs'
import ScrollColumn from '@/components/ui/ScrollColumn'
import GeneralTab from '@/components/settings/GeneralTab'
import LlmTab from '@/components/settings/LlmTab'
import ModelsTab from '@/components/settings/ModelsTab'
import SystemTab from '@/components/settings/SystemTab'
import CacheTab from '@/components/settings/CacheTab'
import AboutTab from '@/components/settings/AboutTab'
import PdfProcessingTab from '@/components/settings/PdfProcessingTab'
import type { SettingsState } from '@/components/settings/types'

type TabKey =
  | 'general'
  | 'ai_models'
  | 'pdf_processing'
  | 'models'
  | 'system'
  | 'cache'
  | 'about'

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
  libraryRoot: string
  onReset: () => void
  onOpenConfig: () => void
}

export default function SettingsTabs({
  settings,
  setSettings,
  libraryRoot,
  onReset,
  onOpenConfig,
}: Props) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<TabKey>('general')

  const tabs = useMemo(() => [
    { key: 'general', label: t('settings.tabs.general') },
    { key: 'ai_models', label: t('settings.tabs.aiModels') },
    { key: 'pdf_processing', label: t('settings.tabs.pdfProcessing') },
    { key: 'models', label: t('settings.tabs.models') },
    { key: 'system', label: t('settings.tabs.system') },
    { key: 'cache', label: t('settings.tabs.cache') },
    { key: 'about', label: t('settings.tabs.about') },
  ], [t])

  return (
    <div className="settings-tabs">
      <Tabs
        items={tabs}
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as TabKey)}
        variant="underline"
        size="sm"
      />
      <ScrollColumn>
        <div className="settings-tab-content">
          {activeTab === 'general' && (
            <GeneralTab settings={settings} setSettings={setSettings} />
          )}
          {activeTab === 'ai_models' && (
            <LlmTab settings={settings} setSettings={setSettings} />
          )}
          {activeTab === 'pdf_processing' && (
            <PdfProcessingTab settings={settings} setSettings={setSettings} />
          )}
          {activeTab === 'models' && (
            <ModelsTab />
          )}
          {activeTab === 'system' && (
            <SystemTab settings={settings} setSettings={setSettings} />
          )}
          {activeTab === 'cache' && <CacheTab libraryRoot={libraryRoot} />}
          {activeTab === 'about' && (
            <AboutTab onReset={onReset} onOpenConfig={onOpenConfig} />
          )}
        </div>
      </ScrollColumn>
    </div>
  )
}