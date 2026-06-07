// AI Models 栏目 — LLM / Embedding / Reranker 三个 tab。
//
// LLM tab 是只读的状态卡 — LLM 由 env (`MBFORGE_LLM_*`) 唯一驱动，
// Settings 不能覆盖；这里只是把 env 当前值 + 联通状态显示出来。
// Embedding / Reranker 还是普通可编辑设置（这部分走 sidecar，与 LLM 无关）。

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import Tabs, { TabPanel } from '../../ui/Tabs'
import SettingSection, { SettingGroup } from '../../ui/SettingSection'
import { TextField, NumberField, CustomField, ProviderField } from '../SettingRow'
import { ModelSelector } from '../ModelComponents'
import LlmStatusCard from '../LlmStatusCard'
import {
  EMBED_MODELS,
  RERANK_MODELS,
  PROVIDER_META,
} from '../modelConfigs'
import type { SettingsState } from '../types'

type Tab = 'llm' | 'embed' | 'rerank'

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

const providerOptions = (map: Record<string, unknown>) =>
  Object.keys(map).map(k => ({
    value: k,
    label: PROVIDER_META[k]?.label ?? k,
  }))

export default function AIModelsSection({ settings, setSettings }: Props) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('llm')

  return (
    <>
      <Tabs
        items={[
          { key: 'llm', label: t('settings.tabLlm') },
          { key: 'embed', label: t('settings.tabEmbed') },
          { key: 'rerank', label: t('settings.tabRerank') },
        ]}
        activeKey={tab}
        onChange={k => setTab(k as Tab)}
        variant="underline"
        size="sm"
      />

      <TabPanel activeKey={tab} tabKey="llm">
        <SettingSection>
          <SettingGroup title={t('settings.llmConfig')}>
            <LlmStatusCard />
          </SettingGroup>
        </SettingSection>
      </TabPanel>

      <TabPanel activeKey={tab} tabKey="embed">
        <SettingSection>
          <SettingGroup title={t('settings.embedConfig')}>
            <ProviderField
              label={t('settings.embedProvider')}
              description={t('settings.embedProviderDesc')}
              provider={settings.embed_provider}
              onProviderChange={v => setSettings(s => ({ ...s, embed_provider: v }))}
              baseUrl={settings.embed_base_url}
              onBaseUrlChange={v => setSettings(s => ({ ...s, embed_base_url: v }))}
              apiKey={settings.embed_api_key}
              onApiKeyChange={v => setSettings(s => ({ ...s, embed_api_key: v }))}
              providerOptions={providerOptions(EMBED_MODELS)}
              needsKey={PROVIDER_META[settings.embed_provider]?.needsKey ?? false}
              baseUrlPlaceholder={PROVIDER_META[settings.embed_provider]?.defaultUrl}
              showBaseUrl={settings.embed_provider === 'openai'}
            />
            <CustomField label={t('settings.model')}>
              <ModelSelector
                provider={settings.embed_provider}
                modelValue={settings.embed_model}
                models={EMBED_MODELS}
                onChange={v => setSettings(s => ({ ...s, embed_model: v }))}
              />
            </CustomField>
            <TextField
              label={t('settings.instruction')}
              description={t('settings.instructionDesc')}
              value={settings.embed_instruction}
              onChange={v => setSettings(s => ({ ...s, embed_instruction: v }))}
              placeholder={t('settings.instructionPlaceholder')}
            />
          </SettingGroup>

          <SettingGroup title={t('settings.embedRuntime')}>
            <ProviderField
              label={t('settings.device')}
              description={t('settings.deviceDesc')}
              provider={settings.embed_device}
              onProviderChange={v => setSettings(s => ({ ...s, embed_device: v as SettingsState['embed_device'] }))}
              baseUrl=""
              onBaseUrlChange={() => {}}
              apiKey=""
              onApiKeyChange={() => {}}
              providerOptions={[
                { value: 'cpu', label: 'CPU' },
                { value: 'cuda', label: 'CUDA' },
                { value: 'auto', label: 'Auto' },
              ]}
              needsKey={false}
              showBaseUrl={false}
            />
            <NumberField
              label={t('settings.mrlDim')}
              description={t('settings.mrlDimDesc')}
              value={settings.embed_mrl_dim}
              onChange={v => setSettings(s => ({ ...s, embed_mrl_dim: v }))}
              min={0}
              max={4096}
              step={64}
              width={100}
              placeholder="0"
            />
          </SettingGroup>
        </SettingSection>
      </TabPanel>

      <TabPanel activeKey={tab} tabKey="rerank">
        <SettingSection>
          <SettingGroup title={t('settings.rerankConfig')}>
            <ProviderField
              label={t('settings.rerankProvider')}
              description={t('settings.rerankProviderDesc')}
              provider={settings.rerank_provider}
              onProviderChange={v => setSettings(s => ({ ...s, rerank_provider: v }))}
              baseUrl=""
              onBaseUrlChange={() => {}}
              apiKey=""
              onApiKeyChange={() => {}}
              providerOptions={providerOptions(RERANK_MODELS)}
              needsKey={false}
              showBaseUrl={false}
            />
            <CustomField label={t('settings.model')}>
              <ModelSelector
                provider={settings.rerank_provider}
                modelValue={settings.rerank_model}
                models={RERANK_MODELS}
                onChange={v => setSettings(s => ({ ...s, rerank_model: v }))}
              />
            </CustomField>
          </SettingGroup>

          <SettingGroup title={t('settings.rerankRuntime')}>
            <ProviderField
              label={t('settings.device')}
              description={t('settings.deviceDesc')}
              provider={settings.rerank_device}
              onProviderChange={v => setSettings(s => ({ ...s, rerank_device: v as SettingsState['rerank_device'] }))}
              baseUrl=""
              onBaseUrlChange={() => {}}
              apiKey=""
              onApiKeyChange={() => {}}
              providerOptions={[
                { value: 'cpu', label: 'CPU' },
                { value: 'cuda', label: 'CUDA' },
                { value: 'auto', label: 'Auto' },
              ]}
              needsKey={false}
              showBaseUrl={false}
            />
            <NumberField
              label={t('settings.maxLength')}
              description={t('settings.maxLengthDesc')}
              value={settings.rerank_max_length}
              onChange={v => setSettings(s => ({ ...s, rerank_max_length: v }))}
              min={128}
              max={32768}
              step={256}
              width={120}
              placeholder="8192"
            />
          </SettingGroup>
        </SettingSection>
      </TabPanel>
    </>
  )
}
