// 视觉模型栏目 — VLM（视觉-语言）+ OCR（文档文字识别）。
// 两个 tab，每个独立配置。

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import Tabs, { TabPanel } from '../../ui/Tabs'
import SettingSection, { SettingGroup } from '../../ui/SettingSection'
import { CustomField, ProviderField, ToggleField } from '../SettingRow'
import { ModelSelector } from '../ModelComponents'
import { VLM_MODELS, OCR_MODELS, PROVIDER_META } from '../modelConfigs'
import type { SettingsState } from '../types'

type Tab = 'vlm' | 'ocr'

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

const providerOptions = (map: Record<string, unknown>) =>
  Object.keys(map).map(k => ({
    value: k,
    label: PROVIDER_META[k]?.label ?? k,
  }))

export default function VisionSection({ settings, setSettings }: Props) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('vlm')

  return (
    <>
      <Tabs
        items={[
          { key: 'vlm', label: 'VLM' },
          { key: 'ocr', label: 'OCR' },
        ]}
        activeKey={tab}
        onChange={k => setTab(k as Tab)}
        variant="underline"
        size="sm"
      />

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
