// PageIndex LLM 配置栏目 — PageIndex tree reasoning + dense rerank 用 LLM。

import { useTranslation } from 'react-i18next'
import SettingSection, { SettingGroup } from '@/components/ui/SettingSection'
import { TextField, NumberField, SelectField } from './SettingRow'
import type { SettingsState } from './types'

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

const PROVIDER_OPTIONS = [
  { value: 'openai_compatible', label: 'OpenAI Compatible' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'anthropic', label: 'Anthropic' },
]

export default function PageindexLlmSection({ settings, setSettings }: Props) {
  const { t } = useTranslation()
  return (
    <SettingSection>
      <SettingGroup title={t('settings.pageindexLlm')}>
        <SelectField
          label={t('settings.llmProvider')}
          description={t('settings.llmProviderDesc')}
          value={settings.pageindex_llm_provider}
          options={PROVIDER_OPTIONS}
          onChange={v => setSettings(s => ({ ...s, pageindex_llm_provider: v }))}
        />
        <TextField
          label={t('settings.llmModel')}
          description={t('settings.llmModelDesc')}
          value={settings.pageindex_llm_model}
          onChange={v => setSettings(s => ({ ...s, pageindex_llm_model: v }))}
          placeholder="gpt-4o-mini"
        />
        <TextField
          label={t('settings.llmBaseUrl')}
          description={t('settings.llmBaseUrlDesc')}
          value={settings.pageindex_llm_base_url}
          onChange={v => setSettings(s => ({ ...s, pageindex_llm_base_url: v }))}
          placeholder="https://api.openai.com/v1"
          monospace
        />
        <TextField
          label="API Key"
          description={t('settings.llmApiKeyDesc')}
          value={settings.pageindex_llm_api_key}
          onChange={v => setSettings(s => ({ ...s, pageindex_llm_api_key: v }))}
          type="password"
          monospace
        />
        <NumberField
          label={t('settings.llmMaxTokens')}
          description={t('settings.llmMaxTokensDesc')}
          value={settings.pageindex_llm_max_tokens}
          onChange={v => setSettings(s => ({ ...s, pageindex_llm_max_tokens: v }))}
          min={256}
          max={128000}
          step={256}
        />
        <NumberField
          label={t('settings.llmTemperature')}
          description={t('settings.llmTemperatureDesc')}
          value={settings.pageindex_llm_temperature}
          onChange={v => setSettings(s => ({ ...s, pageindex_llm_temperature: v }))}
          min={0}
          max={2}
          step={0.1}
          width={100}
        />
        <NumberField
          label={t('settings.pageindexThreshold')}
          description={t('settings.pageindexThresholdDesc')}
          value={settings.pageindex_llm_threshold}
          onChange={v => setSettings(s => ({ ...s, pageindex_llm_threshold: v }))}
          min={1}
          max={100}
          step={1}
        />
      </SettingGroup>
    </SettingSection>
  )
}
