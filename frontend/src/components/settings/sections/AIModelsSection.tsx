// AI Models 栏目 — LLM / Embedding / Reranker / VLM / OCR 五个 tab。
// 所有子页共享 ModelConfigCard，风格统一且全部可编辑。

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import Tabs, { TabPanel } from '../../ui/Tabs'
import ModelConfigCard from '../ModelConfigCard'
import SectionTitle from '../../ui/SectionTitle'
import type { SettingsState } from '../types'

type Tab = 'llm' | 'embed' | 'rerank' | 'vlm' | 'ocr'

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

const TAB_CONFIG: Record<Tab, { titleKey: string; descKey?: string; showTest?: boolean }> = {
  llm: { titleKey: 'settings.tabLlm', descKey: 'settings.tabLlmDesc', showTest: true },
  embed: { titleKey: 'settings.tabEmbed', descKey: 'settings.tabEmbedDesc' },
  rerank: { titleKey: 'settings.tabRerank', descKey: 'settings.tabRerankDesc' },
  vlm: { titleKey: 'settings.tabVlm', descKey: 'settings.tabVlmDesc' },
  ocr: { titleKey: 'settings.tabOcr', descKey: 'settings.tabOcrDesc' },
}

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
        items={[
          { key: 'llm', label: t('settings.tabLlm') },
          { key: 'embed', label: t('settings.tabEmbed') },
          { key: 'rerank', label: t('settings.tabRerank') },
          { key: 'vlm', label: t('settings.tabVlm') },
          { key: 'ocr', label: t('settings.tabOcr') },
        ]}
        activeKey={tab}
        onChange={k => setTab(k as Tab)}
        variant="segment"
        size="sm"
      />

      <TabPanel activeKey={tab} tabKey="llm" tabsId="ai-models-tabs">
        <ModelConfigCard
          modelType="llm"
          title={t(TAB_CONFIG.llm.titleKey)}
          description={TAB_CONFIG.llm.descKey ? t(TAB_CONFIG.llm.descKey) : undefined}
          settings={settings}
          setSettings={setSettings}
          showTest={TAB_CONFIG.llm.showTest}
        />
      </TabPanel>

      <TabPanel activeKey={tab} tabKey="embed" tabsId="ai-models-tabs">
        <ModelConfigCard
          modelType="embed"
          title={t(TAB_CONFIG.embed.titleKey)}
          description={TAB_CONFIG.embed.descKey ? t(TAB_CONFIG.embed.descKey) : undefined}
          settings={settings}
          setSettings={setSettings}
        />
      </TabPanel>

      <TabPanel activeKey={tab} tabKey="rerank" tabsId="ai-models-tabs">
        <ModelConfigCard
          modelType="rerank"
          title={t(TAB_CONFIG.rerank.titleKey)}
          description={TAB_CONFIG.rerank.descKey ? t(TAB_CONFIG.rerank.descKey) : undefined}
          settings={settings}
          setSettings={setSettings}
        />
      </TabPanel>

      <TabPanel activeKey={tab} tabKey="vlm" tabsId="ai-models-tabs">
        <ModelConfigCard
          modelType="vlm"
          title={t(TAB_CONFIG.vlm.titleKey)}
          description={TAB_CONFIG.vlm.descKey ? t(TAB_CONFIG.vlm.descKey) : undefined}
          settings={settings}
          setSettings={setSettings}
        />
      </TabPanel>

      <TabPanel activeKey={tab} tabKey="ocr" tabsId="ai-models-tabs">
        <ModelConfigCard
          modelType="ocr"
          title={t(TAB_CONFIG.ocr.titleKey)}
          description={TAB_CONFIG.ocr.descKey ? t(TAB_CONFIG.ocr.descKey) : undefined}
          settings={settings}
          setSettings={setSettings}
        />
      </TabPanel>
    </div>
  )
}
