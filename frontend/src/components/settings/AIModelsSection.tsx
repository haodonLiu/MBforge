// AI Models 栏目 — LLM / VLM / OCR 三个 tab。
// 所有子页共享 ModelConfigCard，风格统一且全部可编辑。

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import Tabs, { TabPanel } from '../ui/Tabs'
import ModelConfigCard from './ModelConfigCard'
import SectionTitle from '../ui/SectionTitle'
import type { SettingsState } from './types'

type Tab = 'llm' | 'vlm' | 'ocr'

interface TabConfig {
  key: Tab
  titleKey: string
  descKey?: string
  showTest?: boolean
}

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

const TABS: TabConfig[] = [
  { key: 'llm', titleKey: 'settings.tabLlm', descKey: 'settings.tabLlmDesc', showTest: true },
  { key: 'vlm', titleKey: 'settings.tabVlm', descKey: 'settings.tabVlmDesc' },
  { key: 'ocr', titleKey: 'settings.tabOcr', descKey: 'settings.tabOcrDesc' },
]

export default function AIModelsSection({ settings, setSettings }: Props) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('llm')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
      <div>
        <SectionTitle>{t('settings.aiModels')}</SectionTitle>
        <p style={{ margin: 'var(--space-1) 0 0', fontSize: 'var(--font-size-small)', color: 'var(--text-secondary)' }}>
          {t('settings.aiModelsDesc')}
        </p>
      </div>

      <Tabs
        id="ai-models-tabs"
        items={TABS.map(({ key, titleKey }) => ({ key, label: t(titleKey) }))}
        activeKey={tab}
        onChange={k => setTab(k as Tab)}
        variant="segment"
        size="sm"
      />

      {TABS.map(({ key, titleKey, descKey, showTest }) => (
        <TabPanel key={key} activeKey={tab} tabKey={key} tabsId="ai-models-tabs">
          <ModelConfigCard
            modelType={key}
            title={t(titleKey)}
            description={descKey ? t(descKey) : undefined}
            settings={settings}
            setSettings={setSettings}
            showTest={showTest}
          />
        </TabPanel>
      ))}
    </div>
  )
}
