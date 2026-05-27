import { useState, useEffect } from 'react'
import { SettingsIcon, XIcon } from './icons'
import { getSettings, saveSettings } from '../api/settings'
import ErrorBanner from './ErrorBanner'

type Section = 'general' | 'ai' | 'embedding' | 'reranker' | 'appearance' | 'server' | 'about'

const SECTIONS: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: 'general', label: '通用', icon: <SettingsIcon size={18} /> },
  { id: 'ai', label: 'AI 模型', icon: <SettingsIcon size={18} /> },
  { id: 'embedding', label: 'Embedding', icon: <SettingsIcon size={18} /> },
  { id: 'reranker', label: 'Reranker', icon: <SettingsIcon size={18} /> },
  { id: 'appearance', label: '外观', icon: <SettingsIcon size={18} /> },
  { id: 'server', label: '模型服务', icon: <SettingsIcon size={18} /> },
  { id: 'about', label: '关于', icon: <SettingsIcon size={18} /> },
]

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
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function SettingsModal({ open, onClose }: Props) {
  const [activeSection, setActiveSection] = useState<Section>('general')
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [saveSuccess, setSaveSuccess] = useState(false)

  useEffect(() => {
    if (open) {
      loadSettings()
    }
  }, [open])

  const loadSettings = async () => {
    setIsLoading(true)
    try {
      const resp = await getSettings()
      if (resp.success && resp.settings) {
        const s = resp.settings
        setSettings({
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
        })
      }
    } catch (e) {
      console.error(e)
    } finally {
      setIsLoading(false)
    }
  }

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
      }
      const resp = await saveSettings(payload)
      if (resp.success) {
        setSaveSuccess(true)
        setTimeout(() => setSaveSuccess(false), 3000)
      } else {
        setError(resp.error || 'Failed to save settings')
      }
    } catch (e) {
      console.error(e)
      setError('Failed to save settings')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCancel = () => {
    loadSettings()
  }

  const updateSetting = (key: keyof SettingsState, value: string) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  const renderSection = () => {
    switch (activeSection) {
      case 'general':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">项目</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">自动打开最近项目</div>
                  <div className="setting-desc">启动时自动加载上次使用的项目</div>
                </div>
                <label className="toggle">
                  <input type="checkbox" defaultChecked />
                  <span className="toggle-slider"></span>
                </label>
              </div>
            </div>
            <div className="settings-group">
              <h3 className="settings-group-title">语言</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">界面语言</div>
                </div>
                <select
                  className="settings-select"
                  value={settings.language}
                  onChange={e => updateSetting('language', e.target.value)}
                >
                  <option value="zh">中文</option>
                  <option value="en">English</option>
                </select>
              </div>
            </div>
          </div>
        )
      case 'ai':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">LLM 配置</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Provider</div>
                </div>
                <select
                  className="settings-select"
                  value={settings.llm_provider}
                  onChange={e => updateSetting('llm_provider', e.target.value)}
                >
                  <option value="openai_compatible">OpenAI Compatible</option>
                  <option value="anthropic">Anthropic</option>
                </select>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Base URL</div>
                </div>
                <input
                  className="settings-input"
                  value={settings.llm_base_url}
                  onChange={e => updateSetting('llm_base_url', e.target.value)}
                  placeholder="http://localhost:8000/v1"
                />
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">API Key</div>
                </div>
                <input
                  className="settings-input"
                  type="password"
                  value={settings.llm_api_key}
                  onChange={e => updateSetting('llm_api_key', e.target.value)}
                  placeholder="sk-..."
                />
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Model</div>
                </div>
                <input
                  className="settings-input"
                  value={settings.llm_model}
                  onChange={e => updateSetting('llm_model', e.target.value)}
                  placeholder="gpt-4"
                />
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Max Tokens</div>
                  <div className="setting-desc">回复最大 token 数（建议设为模型上限的 1/2）</div>
                </div>
                <input
                  className="setting-input"
                  type="number"
                  value={settings.llm_max_tokens}
                  onChange={e => setSettings(prev => ({ ...prev, llm_max_tokens: parseInt(e.target.value) || 4096 }))}
                  min={256}
                  max={128000}
                  step={256}
                  style={{ width: '120px' }}
                />
              </div>
            </div>
          </div>
        )
      case 'embedding':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">Embedding 配置</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Provider</div>
                </div>
                <select
                  className="settings-select"
                  value={settings.embed_provider}
                  onChange={e => updateSetting('embed_provider', e.target.value)}
                >
                  <option value="qwen3">Qwen3</option>
                  <option value="sentence_transformers">Sentence Transformers</option>
                  <option value="openai">OpenAI</option>
                </select>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Model</div>
                </div>
                <input
                  className="settings-input"
                  value={settings.embed_model}
                  onChange={e => updateSetting('embed_model', e.target.value)}
                  placeholder="Qwen/Qwen3-Embedding-0.6B"
                />
              </div>
            </div>
          </div>
        )
      case 'reranker':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">Reranker 配置</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Provider</div>
                </div>
                <select
                  className="settings-select"
                  value={settings.rerank_provider}
                  onChange={e => updateSetting('rerank_provider', e.target.value)}
                >
                  <option value="qwen3">Qwen3</option>
                  <option value="sentence_transformers">Sentence Transformers</option>
                </select>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Model</div>
                </div>
                <input
                  className="settings-input"
                  value={settings.rerank_model}
                  onChange={e => updateSetting('rerank_model', e.target.value)}
                  placeholder="BAAI/bge-reranker-v2-m3"
                />
              </div>
            </div>
          </div>
        )
      case 'appearance':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">外观</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">主题</div>
                </div>
                <select
                  className="settings-select"
                  value={settings.theme}
                  onChange={e => updateSetting('theme', e.target.value)}
                >
                  <option value="dark">深色</option>
                  <option value="light">浅色</option>
                </select>
              </div>
            </div>
          </div>
        )
      case 'server':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">模型服务</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">服务地址</div>
                  <div className="setting-desc">127.0.0.1:18792</div>
                </div>
              </div>
            </div>
          </div>
        )
      case 'about':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">关于 MBForge</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">版本</div>
                  <div className="setting-desc">0.1.0</div>
                </div>
              </div>
            </div>
          </div>
        )
      default:
        return null
    }
  }

  if (!open) return null

  return (
    <div
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
      <div
        onClick={onClose}
        style={{
          position: 'absolute',
          inset: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          backdropFilter: 'blur(4px)',
        }}
      />

      {/* Modal */}
      <div
        style={{
          position: 'relative',
          width: '90%',
          maxWidth: '800px',
          height: '80%',
          maxHeight: '600px',
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
          <h2 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>设置</h2>
          <button
            onClick={onClose}
            style={{
              width: '32px',
              height: '32px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: '6px',
              border: 'none',
              background: 'transparent',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover)'}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          >
            <XIcon size={18} />
          </button>
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
            {SECTIONS.map(section => (
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
                {section.icon}
                <span>{section.label}</span>
              </button>
            ))}
          </div>

          {/* Right content */}
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}>
            <div style={{
              padding: '16px 20px',
              borderBottom: '1px solid var(--border)',
            }}>
              <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>
                {SECTIONS.find(s => s.id === activeSection)?.label}
              </h3>
            </div>

            <div style={{ flex: 1, padding: '16px 20px', overflowY: 'auto' }}>
              {error && <ErrorBanner message={error} onDismiss={() => setError('')} />}
              {saveSuccess && (
                <div style={{
                  padding: '10px 16px',
                  background: 'rgba(34, 197, 94, 0.1)',
                  border: '1px solid rgba(34, 197, 94, 0.3)',
                  borderRadius: '6px',
                  color: '#22c55e',
                  fontSize: '13px',
                  marginBottom: '12px',
                }}>
                  设置已保存
                </div>
              )}
              {renderSection()}
            </div>

            {/* Footer */}
            <div style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '8px',
              padding: '12px 20px',
              borderTop: '1px solid var(--border)',
            }}>
              <button className="btn btn-secondary" onClick={handleCancel} disabled={isLoading}>
                取消
              </button>
              <button className="btn btn-primary" onClick={handleSave} disabled={isLoading}>
                {isLoading ? '保存中...' : '保存设置'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
