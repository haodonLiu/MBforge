import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import i18n from '../i18n'
import { SettingsIcon, XIcon, DownloadIcon } from './icons'
import { getSettings, saveSettings } from '../api/settings'
import { useTheme } from '../hooks/useTheme'
import { fadeIn, modalEntrance } from '../hooks/useAnimations'
import AlertBanner from './ui/AlertBanner'
import Button from './ui/Button'
import IconButton from './ui/IconButton'
import Input from './ui/Input'
import SettingSection, { SettingGroup, SettingItem } from './ui/SettingSection'
import { showToast } from '../hooks/useToast'
import { EnvironmentSection, ModelsTab, ModelSelector } from './settings'
import { SETTING_SECTIONS, LLM_MODELS, EMBED_MODELS, RERANK_MODELS, type Section } from './settings/modelConfigs'

// ============ Types ============
interface SettingsState {
  theme: string
  language: string
  llm_provider: string
  llm_base_url: string
  llm_api_key: string
  llm_model: string
  llm_max_tokens: number
  embed_provider: string
  embed_model: string
  rerank_provider: string
  rerank_model: string
  model_cache_dir: string
}

const DEFAULT_SETTINGS: SettingsState = {
  theme: 'dark',
  language: 'zh',
  llm_provider: 'openai_compatible',
  llm_base_url: 'http://localhost:8000/v1',
  llm_api_key: '',
  llm_model: 'default',
  llm_max_tokens: 4096,
  embed_provider: 'qwen3',
  embed_model: 'Qwen/Qwen3-Embedding-0.6B',
  rerank_provider: 'qwen3',
  rerank_model: 'BAAI/bge-reranker-v2-m3',
  model_cache_dir: '',
}

// ============ Section Renderers ============
function GeneralSection({ settings, updateSetting }: { settings: SettingsState; updateSetting: (k: keyof SettingsState, v: string) => void }) {
  const { t } = useTranslation()
  return (
    <SettingSection>
      <SettingGroup title={t('settings.llmConfig')}>
        <SettingItem
          title={t('settings.autoOpenProject')}
          description={t('settings.autoOpenProjectDesc')}
        >
          <label className="toggle">
            <input type="checkbox" defaultChecked />
            <span className="toggle-slider"></span>
          </label>
        </SettingItem>
      </SettingGroup>
      <SettingGroup title={t('settings.language')}>
        <SettingItem title={t('settings.language')}>
          <select
            className="settings-select"
            value={settings.language}
            onChange={e => updateSetting('language', e.target.value)}
          >
            <option value="zh">中文</option>
            <option value="en">English</option>
          </select>
        </SettingItem>
      </SettingGroup>
    </SettingSection>
  )
}

function AISection({ settings, updateSetting, setSettings }: { settings: SettingsState; updateSetting: (k: keyof SettingsState, v: string) => void; setSettings: React.Dispatch<React.SetStateAction<SettingsState>> }) {
  const { t } = useTranslation()
  return (
    <SettingSection>
      <SettingGroup title={t('settings.llmConfig')}>
        <SettingItem
          title={t('settings.llmProvider')}
          description={t('settings.llmProviderDesc')}
        >
          <select
            className="settings-select"
            value={settings.llm_provider}
            onChange={e => {
              updateSetting('llm_provider', e.target.value)
              const models = LLM_MODELS[e.target.value]
              if (models.length > 0) {
                updateSetting('llm_model', models[0].value)
              }
            }}
          >
            <option value="openai_compatible">OpenAI Compatible</option>
            <option value="anthropic">Anthropic</option>
            <option value="ollama">Ollama（本地）</option>
          </select>
        </SettingItem>
        <SettingItem
          title={t('settings.baseUrl')}
          description={settings.llm_provider === 'ollama' ? '默认: http://localhost:11434' : t('settings.baseUrlDesc')}
        >
          <Input
            className="settings-input"
            value={settings.llm_base_url}
            onChange={e => updateSetting('llm_base_url', e.target.value)}
            placeholder={
              settings.llm_provider === 'ollama'
                ? 'http://localhost:11434'
                : 'http://localhost:8000/v1'
            }
          />
        </SettingItem>
        {settings.llm_provider !== 'ollama' && (
          <SettingItem title={t('settings.apiKey')}>
            <Input
              className="settings-input"
              type="password"
              value={settings.llm_api_key}
              onChange={e => updateSetting('llm_api_key', e.target.value)}
              placeholder="sk-..."
            />
          </SettingItem>
        )}
        <SettingItem title={t('settings.model')} description={t('settings.modelDesc')} layout="stacked">
          <ModelSelector
            provider={settings.llm_provider}
            modelValue={settings.llm_model}
            models={LLM_MODELS}
            onChange={v => updateSetting('llm_model', v)}
          />
        </SettingItem>
        <SettingItem title={t('settings.maxTokens')} description={t('settings.maxTokensDesc')}>
          <input
            className="settings-input"
            type="number"
            value={settings.llm_max_tokens}
            onChange={e => setSettings(prev => ({ ...prev, llm_max_tokens: parseInt(e.target.value) || 4096 }))}
            min={256}
            max={128000}
            step={256}
            style={{ width: '120px', minWidth: '120px', maxWidth: '120px' }}
          />
        </SettingItem>
      </SettingGroup>
    </SettingSection>
  )
}

function EmbeddingSection({ settings, updateSetting }: { settings: SettingsState; updateSetting: (k: keyof SettingsState, v: string) => void }) {
  const { t } = useTranslation()
  return (
    <SettingSection>
      <SettingGroup title={t('settings.embedConfig')}>
        <SettingItem
          title={t('settings.llmProvider')}
          description={t('settings.embedProviderDesc')}
        >
          <select
            className="settings-select"
            value={settings.embed_provider}
            onChange={e => {
              updateSetting('embed_provider', e.target.value)
              const models = EMBED_MODELS[e.target.value]
              if (models.length > 0) {
                updateSetting('embed_model', models[0].value)
              }
            }}
          >
            <option value="qwen3">Qwen3（本地）</option>
            <option value="sentence_transformers">Sentence Transformers（本地）</option>
            <option value="openai">OpenAI（API）</option>
          </select>
        </SettingItem>
        <SettingItem title={t('settings.model')} layout="stacked">
          <ModelSelector
            provider={settings.embed_provider}
            modelValue={settings.embed_model}
            models={EMBED_MODELS}
            onChange={v => updateSetting('embed_model', v)}
          />
        </SettingItem>
      </SettingGroup>
    </SettingSection>
  )
}

function RerankerSection({ settings, updateSetting }: { settings: SettingsState; updateSetting: (k: keyof SettingsState, v: string) => void }) {
  const { t } = useTranslation()
  return (
    <SettingSection>
      <SettingGroup title={t('settings.rerankConfig')}>
        <SettingItem
          title={t('settings.llmProvider')}
          description={t('settings.rerankProviderDesc')}
        >
          <select
            className="settings-select"
            value={settings.rerank_provider}
            onChange={e => {
              updateSetting('rerank_provider', e.target.value)
              const models = RERANK_MODELS[e.target.value]
              if (models.length > 0) {
                updateSetting('rerank_model', models[0].value)
              }
            }}
          >
            <option value="qwen3">Qwen3（本地）</option>
            <option value="sentence_transformers">Sentence Transformers（本地）</option>
          </select>
        </SettingItem>
        <SettingItem title={t('settings.model')} layout="stacked">
          <ModelSelector
            provider={settings.rerank_provider}
            modelValue={settings.rerank_model}
            models={RERANK_MODELS}
            onChange={v => updateSetting('rerank_model', v)}
          />
        </SettingItem>
      </SettingGroup>
    </SettingSection>
  )
}

function AppearanceSection({ settings, updateSetting }: { settings: SettingsState; updateSetting: (k: keyof SettingsState, v: string) => void }) {
  const { t } = useTranslation()
  return (
    <SettingSection>
      <SettingGroup title={t('settings.appearance')}>
        <SettingItem title={t('settings.theme')}>
          <select
            className="settings-select"
            value={settings.theme}
            onChange={e => updateSetting('theme', e.target.value)}
          >
            <option value="dark">{t('settings.dark')}</option>
            <option value="light">{t('settings.light')}</option>
          </select>
        </SettingItem>
      </SettingGroup>
    </SettingSection>
  )
}

function ServerSection() {
  const { t } = useTranslation()
  return (
    <SettingSection>
      <SettingGroup title={t('settings.modelService')}>
        <SettingItem title={t('settings.serverAddress')} description="127.0.0.1:18792" />
      </SettingGroup>
    </SettingSection>
  )
}

function AboutSection() {
  const { t } = useTranslation()
  return (
    <SettingSection>
      <SettingGroup title={t('settings.aboutMbforge')}>
        <SettingItem title={t('settings.version')} description="0.2.0" />
      </SettingGroup>
    </SettingSection>
  )
}

// ============ Section Icon Map ============
const SECTION_ICONS: Record<string, React.ReactNode> = {
  settings: <SettingsIcon size={18} />,
  download: <DownloadIcon size={18} />,
}

// ============ Main Component ============
interface Props {
  open: boolean
  onClose: () => void
}

export default function SettingsModal({ open, onClose }: Props) {
  const [activeSection, setActiveSection] = useState<Section>('general')
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS)
  const [initialSettings, setInitialSettings] = useState<SettingsState>(DEFAULT_SETTINGS)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [saveSuccess, setSaveSuccess] = useState(false)

  const { t } = useTranslation()

  // 脏状态检测
  const isDirty = JSON.stringify(settings) !== JSON.stringify(initialSettings)

  const confirmClose = useCallback(() => {
    if (isDirty && !window.confirm(t('settings.unsavedChanges'))) {
      return
    }
    onClose()
  }, [isDirty, onClose, t])
  const { setTheme } = useTheme()

  const loadSettings = useCallback(async () => {
    setIsLoading(true)
    try {
      const resp = await getSettings()
      if (resp.success && resp.settings) {
        const s = resp.settings
        const loaded = {
          theme: s.theme || 'dark',
          language: s.language || 'zh',
          llm_provider: s.llm?.provider || 'openai_compatible',
          llm_base_url: s.llm?.base_url || '',
          llm_api_key: s.llm?.api_key || '',
          llm_model: s.llm?.model_name || '',
          llm_max_tokens: s.llm?.max_tokens || 4096,
          embed_provider: s.embed?.provider || 'qwen3',
          embed_model: s.embed?.model_name || '',
          rerank_provider: s.rerank?.provider || 'qwen3',
          rerank_model: s.rerank?.model_name || '',
          model_cache_dir: s.model_cache_dir || '',
        }
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
      const payload = {
        theme: settings.theme,
        language: settings.language,
        llm: {
          provider: settings.llm_provider,
          base_url: settings.llm_base_url,
          api_key: settings.llm_api_key,
          model_name: settings.llm_model,
          max_tokens: settings.llm_max_tokens,
        },
        embed: {
          provider: settings.embed_provider,
          model_name: settings.embed_model,
        },
        rerank: {
          provider: settings.rerank_provider,
          model_name: settings.rerank_model,
        },
        model_cache_dir: settings.model_cache_dir,
      }
      const resp = await saveSettings(payload)
      if (resp.success) {
        setSaveSuccess(true)
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

  const updateSetting = (key: keyof SettingsState, value: string) => {
    setSettings(prev => ({ ...prev, [key]: value }))
    if (key === 'theme') {
      setTheme(value as 'light' | 'dark')
    }
    if (key === 'language') {
      void i18n.changeLanguage(value)
    }
  }

  useEffect(() => {
    if (open) {
      void loadSettings()
    }
  }, [open, loadSettings])

  // Render section content
  const renderSection = () => {
    switch (activeSection) {
      case 'general':
        return <GeneralSection settings={settings} updateSetting={updateSetting} />
      case 'ai':
        return <AISection settings={settings} updateSetting={updateSetting} setSettings={setSettings} />
      case 'embedding':
        return <EmbeddingSection settings={settings} updateSetting={updateSetting} />
      case 'reranker':
        return <RerankerSection settings={settings} updateSetting={updateSetting} />
      case 'models':
        return <ModelsTab />
      case 'environment':
        return <EnvironmentSection />
      case 'appearance':
        return <AppearanceSection settings={settings} updateSetting={updateSetting} />
      case 'server':
        return <ServerSection />
      case 'about':
        return <AboutSection />
      default:
        return null
    }
  }

  if (!open) return null

  const sectionData = SETTING_SECTIONS.find(s => s.id === activeSection)

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
          {/* Backdrop */}
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

          {/* Modal */}
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
                {SETTING_SECTIONS.map(section => (
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
                    {SECTION_ICONS[section.icon] || <SettingsIcon size={18} />}
                    <span>{t(section.labelKey)}</span>
                  </button>
                ))}
              </div>

              {/* Right content */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
                  <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>
                    {sectionData ? t(sectionData.labelKey) : ''}
                  </h3>
                </div>

                <div style={{ flex: 1, padding: '16px 20px', overflowY: 'auto' }}>
                  {error && <AlertBanner variant="danger" message={error} onDismiss={() => setError('')} />}
                  {saveSuccess && <AlertBanner variant="success" message={t('settings.saved')} />}
                  <motion.div key={activeSection} variants={fadeIn} initial="hidden" animate="visible">
                    {renderSection()}
                  </motion.div>
                </div>

                {/* Footer */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '8px',
                  padding: '12px 20px',
                  borderTop: '1px solid var(--border)',
                }}>
                  <Button variant="secondary" onClick={loadSettings} disabled={isLoading}>
                    {t('common.cancel')}
                  </Button>
                  <Button variant="primary" onClick={handleSave} disabled={isLoading} loading={isLoading}>
                    {isLoading ? t('settings.saving') : t('common.save')}
                  </Button>
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
    </AnimatePresence>
  )
}
