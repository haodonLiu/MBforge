// AI Models 栏目 — LLM / Embedding / Reranker / VLM / OCR 五个 tab。
//
// 视觉模型（VLM、OCR）从原 VisionSection 合并过来；侧边栏只保留
// "AI 模型" 一项。LLM tab 是只读的状态卡 — LLM 由 env
// (`MBFORGE_LLM_*`) 唯一驱动，Settings 不能覆盖；这里只是把 env 当前值 +
// 联通状态显示出来。其它四个 tab 还是普通可编辑设置（走 sidecar，
// 与 LLM 无关）。

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import Tabs, { TabPanel } from '../../ui/Tabs'
import SettingSection, { SettingGroup } from '../../ui/SettingSection'
import {
  TextField,
  NumberField,
  CustomField,
  ProviderField,
  ToggleField,
} from '../SettingRow'
import { ModelSelector } from '../ModelComponents'
import LlmStatusCard from '../LlmStatusCard'
import {
  EMBED_MODELS,
  RERANK_MODELS,
  VLM_MODELS,
  OCR_MODELS,
  PROVIDER_META,
} from '../modelConfigs'
import type { SettingsState } from '../types'

type Tab = 'llm' | 'embed' | 'rerank' | 'vlm' | 'ocr'

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
          { key: 'vlm', label: t('settings.tabVlm') },
          { key: 'ocr', label: t('settings.tabOcr') },
        ]}
        activeKey={tab}
        onChange={k => setTab(k as Tab)}
        variant="underline"
        size="sm"
      />

      {/* ---------- LLM (read-only env-driven status) ---------- */}
      <TabPanel activeKey={tab} tabKey="llm">
        <SettingSection>
          <SettingGroup title={t('settings.llmConfig')}>
            <LlmStatusCard />
          </SettingGroup>
        </SettingSection>
      </TabPanel>

      {/* ---------- Embedding ---------- */}
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

      {/* ---------- Reranker ---------- */}
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

      {/* ---------- VLM (moved from former VisionSection) ---------- */}
      <TabPanel activeKey={tab} tabKey="vlm">
        <SettingSection>
          <SettingGroup title="VLM">
            <ProviderField
              label={t('settings.vlmProvider')}
              description={t('settings.vlmProviderDesc')}
              provider={settings.vlm_provider}
              onProviderChange={v => setSettings(s => ({ ...s, vlm_provider: v }))}
              baseUrl={settings.vlm_base_url}
              onBaseUrlChange={v => setSettings(s => ({ ...s, vlm_base_url: v }))}
              apiKey={settings.vlm_api_key}
              onApiKeyChange={v => setSettings(s => ({ ...s, vlm_api_key: v }))}
              providerOptions={providerOptions(VLM_MODELS)}
              needsKey={PROVIDER_META[settings.vlm_provider]?.needsKey ?? true}
              baseUrlPlaceholder={PROVIDER_META[settings.vlm_provider]?.defaultUrl}
            />
            <CustomField label={t('settings.model')}>
              <ModelSelector
                provider={settings.vlm_provider}
                modelValue={settings.vlm_model}
                models={VLM_MODELS}
                onChange={v => setSettings(s => ({ ...s, vlm_model: v }))}
              />
            </CustomField>
          </SettingGroup>
        </SettingSection>
      </TabPanel>

      {/* ---------- OCR (moved from former VisionSection) ---------- */}
      <TabPanel activeKey={tab} tabKey="ocr">
        <SettingSection>
          <SettingGroup title="OCR">
            <ProviderField
              label={t('settings.ocrProvider')}
              description={t('settings.ocrProviderDesc')}
              provider={settings.ocr_provider}
              onProviderChange={v => setSettings(s => ({ ...s, ocr_provider: v }))}
              baseUrl={settings.ocr_base_url}
              onBaseUrlChange={v => setSettings(s => ({ ...s, ocr_base_url: v }))}
              apiKey={settings.ocr_api_key}
              onApiKeyChange={v => setSettings(s => ({ ...s, ocr_api_key: v }))}
              providerOptions={providerOptions(OCR_MODELS)}
              needsKey={PROVIDER_META[settings.ocr_provider]?.needsKey ?? false}
              baseUrlPlaceholder={PROVIDER_META[settings.ocr_provider]?.defaultUrl}
            />
            <CustomField label={t('settings.model')}>
              <ModelSelector
                provider={settings.ocr_provider}
                modelValue={settings.ocr_model}
                models={OCR_MODELS}
                onChange={v => setSettings(s => ({ ...s, ocr_model: v }))}
              />
            </CustomField>
          </SettingGroup>

          <SettingGroup title={t('settings.ocrFlags')}>
            <ToggleField
              label={t('settings.useHfMirror')}
              description={t('settings.useHfMirrorDesc')}
              value={settings.ocr_use_hf_mirror}
              onChange={v => setSettings(s => ({ ...s, ocr_use_hf_mirror: v }))}
            />
            <ToggleField
              label={t('settings.usePdfInspector')}
              description={t('settings.usePdfInspectorDesc')}
              value={settings.ocr_use_pdf_inspector}
              onChange={v => setSettings(s => ({ ...s, ocr_use_pdf_inspector: v }))}
            />
          </SettingGroup>
        </SettingSection>
      </TabPanel>
    </>
  )
}
