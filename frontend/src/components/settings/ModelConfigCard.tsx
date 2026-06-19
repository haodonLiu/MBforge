import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getLlmEnvConfig, testLlmConnection, type LlmEnvStatus } from '../../api/tauri/agent'
import { openExternalUrl } from '@/api/tauri/_utils'
import SettingSection, { SettingGroup, SettingItem } from '../ui/SettingSection'
import Button from '../ui/Button'
import Badge, { type BadgeTone } from '../ui/Badge'
import InlineAlert from '../ui/InlineAlert'
import {
  NumberField,
  ProviderField,
  ToggleField,
} from './SettingRow'
import ApiKeyInput from './ApiKeyInput'
import { ModelSelector } from './ModelComponents'
import {
  EMBED_MODELS,
  LLM_MODELS,
  OCR_MODELS,
  PROVIDER_META,
  RERANK_MODELS,
  VLM_MODELS,
  type ModelMap,
} from './modelConfigs'
import type { SettingsState } from './types'

type ModelType = 'llm' | 'embed' | 'rerank' | 'vlm' | 'ocr'

interface Props {
  modelType: ModelType
  title: string
  description?: string
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
  showTest?: boolean
}

const STATUS_TONE: Record<NonNullable<LlmEnvStatus['status']>, BadgeTone> = {
  not_configured: 'warning',
  ok: 'success',
  unreachable: 'danger',
  http_error: 'danger',
  auth_error: 'danger',
}

const providerOptions = (map: ModelMap) =>
  Object.keys(map).map(k => ({
    value: k,
    label: (PROVIDER_META[k] ?? { label: k }).label,
  }))

const getProviderMeta = (key: string) =>
  PROVIDER_META[key] ?? { label: key, defaultUrl: '', needsKey: false }

export default function ModelConfigCard({
  modelType,
  title,
  description,
  settings,
  setSettings,
  showTest,
}: Props) {
  const { t } = useTranslation()
  const [testStatus, setTestStatus] = useState<LlmEnvStatus | null>(null)
  const [testing, setTesting] = useState(false)

  // Load the current active LLM config once on mount (env or saved config).
  // This only reads the resolved config; it does not perform a network probe.
  useEffect(() => {
    if (!showTest) return
    let cancelled = false
    getLlmEnvConfig()
      .then(s => { if (!cancelled) setTestStatus(s) })
      .catch(() => { /* ignore initial load errors; user can hit Test */ })
    return () => { cancelled = true }
  }, [showTest])

  const update = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => {
    setSettings(s => ({ ...s, [key]: value }))
  }

  const runTest = async () => {
    setTesting(true)
    try {
      const s = await testLlmConnection()
      setTestStatus(s)
    } catch (e) {
      setTestStatus({
        provider: '',
        base_url: '',
        api_key_set: false,
        model: '',
        status: 'unreachable',
        error: e instanceof Error ? e.message : String(e),
        http_status: null,
        latency_ms: null,
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="model-config-card" style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 16 }}>
        <div>
          <h3 style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 600 }}>{title}</h3>
          {description && (
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>{description}</p>
          )}
        </div>
        {showTest && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            {testStatus && (
              <Badge tone={testing ? 'loading' : STATUS_TONE[testStatus.status]}>
                {testing ? t('settings.testing') : t(`settings.llmStatus.${testStatus.status}`)}
                {!testing && testStatus.latency_ms != null && ` (${testStatus.latency_ms} ms)`}
              </Badge>
            )}
            <Button size="sm" variant="secondary" onClick={runTest} disabled={testing} loading={testing}>
              {t('settings.testConnection')}
            </Button>
          </div>
        )}
      </div>

      <SettingSection>
        <SettingGroup title={t('settings.connectionGroup')}>
          {modelType === 'llm' && (
            <>
              <ProviderField
                label={t('settings.llmProvider')}
                description={t('settings.llmProviderDesc')}
                provider={settings.llm_provider}
                onProviderChange={v => update('llm_provider', v)}
                baseUrl={settings.llm_base_url}
                onBaseUrlChange={v => update('llm_base_url', v)}
                apiKey={settings.llm_api_key}
                onApiKeyChange={v => update('llm_api_key', v)}
                providerOptions={providerOptions(LLM_MODELS)}
                needsKey={getProviderMeta(settings.llm_provider).needsKey}
                baseUrlPlaceholder={getProviderMeta(settings.llm_provider).defaultUrl}
                baseUrlLabel={t('settings.llmBaseUrl')}
                apiKeyLabel={t('settings.llmApiKey')}
              />
              <SettingItem title={t('settings.llmModel')} layout="stacked">
                <ModelSelector
                  provider={settings.llm_provider}
                  modelValue={settings.llm_model}
                  models={LLM_MODELS}
                  onChange={v => update('llm_model', v)}
                />
              </SettingItem>
            </>
          )}

          {modelType === 'embed' && (
            <>
              <ProviderField
                label={t('settings.embedProvider')}
                description={t('settings.embedProviderDesc')}
                provider={settings.embed_provider}
                onProviderChange={v => update('embed_provider', v)}
                baseUrl={settings.embed_base_url}
                onBaseUrlChange={v => update('embed_base_url', v)}
                apiKey={settings.embed_api_key}
                onApiKeyChange={v => update('embed_api_key', v)}
                providerOptions={providerOptions(EMBED_MODELS)}
                needsKey={getProviderMeta(settings.embed_provider).needsKey}
                baseUrlPlaceholder={getProviderMeta(settings.embed_provider).defaultUrl}
                showBaseUrl={settings.embed_provider === 'openai'}
              />
              <SettingItem title={t('settings.model')} layout="stacked">
                <ModelSelector
                  provider={settings.embed_provider}
                  modelValue={settings.embed_model}
                  models={EMBED_MODELS}
                  onChange={v => update('embed_model', v)}
                />
              </SettingItem>
              <SettingItem title={t('settings.instruction')} layout="stacked">
                <input
                  className="settings-input"
                  type="text"
                  value={settings.embed_instruction}
                  onChange={e => update('embed_instruction', e.target.value)}
                  placeholder={t('settings.instructionPlaceholder')}
                  style={{ width: '100%' }}
                />
              </SettingItem>
            </>
          )}

          {modelType === 'rerank' && (
            <>
              <ProviderField
                label={t('settings.rerankProvider')}
                description={t('settings.rerankProviderDesc')}
                provider={settings.rerank_provider}
                onProviderChange={v => update('rerank_provider', v)}
                baseUrl=""
                onBaseUrlChange={() => {}}
                apiKey=""
                onApiKeyChange={() => {}}
                providerOptions={providerOptions(RERANK_MODELS)}
                needsKey={false}
                showBaseUrl={false}
              />
              <SettingItem title={t('settings.model')} layout="stacked">
                <ModelSelector
                  provider={settings.rerank_provider}
                  modelValue={settings.rerank_model}
                  models={RERANK_MODELS}
                  onChange={v => update('rerank_model', v)}
                />
              </SettingItem>
            </>
          )}

          {modelType === 'vlm' && (
            <>
              <ProviderField
                label={t('settings.vlmProvider')}
                description={t('settings.vlmProviderDesc')}
                provider={settings.vlm_provider}
                onProviderChange={v => update('vlm_provider', v)}
                baseUrl={settings.vlm_base_url}
                onBaseUrlChange={v => update('vlm_base_url', v)}
                apiKey={settings.vlm_api_key}
                onApiKeyChange={v => update('vlm_api_key', v)}
                providerOptions={providerOptions(VLM_MODELS)}
                needsKey={getProviderMeta(settings.vlm_provider).needsKey}
                baseUrlPlaceholder={getProviderMeta(settings.vlm_provider).defaultUrl}
              />
              <SettingItem title={t('settings.model')} layout="stacked">
                <ModelSelector
                  provider={settings.vlm_provider}
                  modelValue={settings.vlm_model}
                  models={VLM_MODELS}
                  onChange={v => update('vlm_model', v)}
                />
              </SettingItem>
            </>
          )}

          {modelType === 'ocr' && (
            <>
              <ProviderField
                label={t('settings.ocrProvider')}
                description={t('settings.ocrProviderDesc')}
                provider={settings.ocr_provider}
                onProviderChange={v => update('ocr_provider', v)}
                baseUrl={settings.ocr_base_url}
                onBaseUrlChange={v => update('ocr_base_url', v)}
                apiKey={settings.ocr_api_key}
                onApiKeyChange={v => update('ocr_api_key', v)}
                providerOptions={providerOptions(OCR_MODELS)}
                needsKey={getProviderMeta(settings.ocr_provider).needsKey}
                baseUrlPlaceholder={getProviderMeta(settings.ocr_provider).defaultUrl}
              />
              <SettingItem title={t('settings.model')} layout="stacked">
                <ModelSelector
                  provider={settings.ocr_provider}
                  modelValue={settings.ocr_model}
                  models={OCR_MODELS}
                  onChange={v => update('ocr_model', v)}
                />
              </SettingItem>
            </>
          )}
        </SettingGroup>

        {modelType === 'llm' && (
          <SettingGroup title={t('settings.llmSampling')}>
            <NumberField
              label={t('settings.maxTokens')}
              description={t('settings.maxTokensDesc')}
              value={settings.llm_max_tokens}
              onChange={v => update('llm_max_tokens', v)}
              min={1}
              max={65536}
              step={128}
              width={120}
            />
            <NumberField
              label={t('settings.temperature')}
              description={t('settings.temperatureDesc')}
              value={settings.llm_temperature}
              onChange={v => update('llm_temperature', v)}
              min={0}
              max={2}
              step={0.1}
              width={100}
            />
            <NumberField
              label={t('settings.topP')}
              description={t('settings.topPDesc')}
              value={settings.llm_top_p}
              onChange={v => update('llm_top_p', v)}
              min={0}
              max={1}
              step={0.05}
              width={100}
            />
            <NumberField
              label={t('settings.requestTimeout')}
              description={t('settings.requestTimeoutDesc')}
              value={settings.llm_request_timeout}
              onChange={v => update('llm_request_timeout', v)}
              min={1}
              max={600}
              step={10}
              width={120}
            />
          </SettingGroup>
        )}

        {modelType === 'embed' && (
          <SettingGroup title={t('settings.embedRuntime')}>
            <ProviderField
              label={t('settings.device')}
              description={t('settings.deviceDesc')}
              provider={settings.embed_device}
              onProviderChange={v => update('embed_device', v as SettingsState['embed_device'])}
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
              onChange={v => update('embed_mrl_dim', v)}
              min={0}
              max={4096}
              step={64}
              width={100}
              placeholder="0"
            />
          </SettingGroup>
        )}

        {modelType === 'rerank' && (
          <SettingGroup title={t('settings.rerankRuntime')}>
            <ProviderField
              label={t('settings.device')}
              description={t('settings.deviceDesc')}
              provider={settings.rerank_device}
              onProviderChange={v => update('rerank_device', v as SettingsState['rerank_device'])}
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
              onChange={v => update('rerank_max_length', v)}
              min={128}
              max={32768}
              step={256}
              width={120}
              placeholder="8192"
            />
          </SettingGroup>
        )}

        {modelType === 'ocr' && (
          <>
            <SettingGroup title={t('settings.ocrFlags')}>
              <ToggleField
                label={t('settings.useHfMirror')}
                description={t('settings.useHfMirrorDesc')}
                value={settings.ocr_use_hf_mirror}
                onChange={v => update('ocr_use_hf_mirror', v)}
              />
              <ToggleField
                label={t('settings.usePdfInspector')}
                description={t('settings.usePdfInspectorDesc')}
                value={settings.ocr_use_pdf_inspector}
                onChange={v => update('ocr_use_pdf_inspector', v)}
              />
            </SettingGroup>
            <OcrBackendKeys settings={settings} setSettings={setSettings} />
          </>
        )}
      </SettingSection>

      {testStatus?.error && (
        <InlineAlert tone="danger" title={t('settings.connectionFailed')} style={{ marginTop: 'var(--space-4)' }}>
          {testStatus.error}
        </InlineAlert>
      )}
    </div>
  )
}

function OcrBackendKeys({ settings, setSettings }: { settings: SettingsState; setSettings: React.Dispatch<React.SetStateAction<SettingsState>> }) {
  const { t } = useTranslation()
  const update = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => {
    setSettings(s => ({ ...s, [key]: value }))
  }

  return (
    <SettingGroup title={t('ocr.backendSection.title')}>
      <p style={{ margin: '0 0 12px', fontSize: 12, color: 'var(--text-muted)' }}>
        {t('ocr.backendSection.desc')}
      </p>
      <BackendKeyRow
        label={t('ocr.config.mineru')}
        placeholder="eyJ0eXBlIjoiSldU..."
        value={settings.ocr_mineru_api_key}
        onChange={v => update('ocr_mineru_api_key', v)}
        getKeyUrl="https://mineru.net/"
        getKeyLabel={t('ocr.config.getKey')}
      />
      <BackendKeyRow
        label={t('ocr.config.uniparser')}
        placeholder="up_..."
        value={settings.ocr_uniparser_api_key}
        onChange={v => update('ocr_uniparser_api_key', v)}
        getKeyUrl="https://uniparser.dp.tech/"
        getKeyLabel={t('ocr.config.getKey')}
      />
      <BackendKeyRow
        label={t('ocr.config.paddleocr')}
        placeholder="bearer token"
        value={settings.ocr_paddleocr_api_key}
        onChange={v => update('ocr_paddleocr_api_key', v)}
        getKeyUrl="https://aistudio.baidu.com/paddleocr"
        getKeyLabel={t('ocr.config.getKey')}
        extra={[
          {
            label: t('ocr.config.paddleocrHost'),
            value: settings.ocr_paddleocr_host,
            onChange: v => update('ocr_paddleocr_host', v),
            placeholder: 'https://paddleocr.aistudio-app.com',
          },
          {
            label: t('ocr.config.paddleocrModel'),
            value: settings.ocr_paddleocr_model,
            onChange: v => update('ocr_paddleocr_model', v),
            placeholder: 'PaddleOCR-VL-1.6',
          },
        ]}
      />
    </SettingGroup>
  )
}

interface BackendKeyRowProps {
  label: string
  placeholder: string
  value: string
  onChange: (v: string) => void
  getKeyUrl?: string
  getKeyLabel?: string
  extra?: Array<{
    label: string
    value: string
    onChange: (v: string) => void
    placeholder: string
  }>
}

function BackendKeyRow({ label, placeholder, value, onChange, getKeyUrl, getKeyLabel, extra }: BackendKeyRowProps) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
          {label}
        </label>
        {getKeyUrl && getKeyLabel && (
          <button
            type="button"
            onClick={() => openExternalUrl(getKeyUrl)}
            style={{
              padding: 0,
              border: 'none',
              background: 'none',
              fontSize: 11,
              color: 'var(--accent)',
              textDecoration: 'underline',
              cursor: 'pointer',
            }}
          >
            {getKeyLabel}
          </button>
        )}
      </div>
      <ApiKeyInput value={value} onChange={onChange} placeholder={placeholder} />
      {extra && extra.length > 0 && (
        <div style={{ marginTop: 8, display: 'grid', gap: 6 }}>
          {extra.map(e => (
            <div key={e.label} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <label style={{ fontSize: 11, color: 'var(--text-muted)', minWidth: 80 }}>{e.label}</label>
              <input
                type="text"
                value={e.value}
                onChange={ev => e.onChange(ev.target.value)}
                placeholder={e.placeholder}
                style={{
                  flex: 1,
                  padding: '6px 8px',
                  fontSize: 12,
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  background: 'var(--bg-base)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono, monospace)',
                }}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const cardStyle: React.CSSProperties = {
  padding: 'var(--space-4)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-lg)',
  background: 'var(--bg-surface)',
  boxShadow: 'var(--shadow-card)',
}
