import { useState, useEffect, useRef, useCallback } from 'react'
import { SettingsIcon, XIcon, DownloadIcon } from './icons'
import { getSettings, saveSettings } from '../api/settings'
import { listModels, downloadModel, type DownloadModel, type ProgressEvent } from '../api/download'
import ErrorBanner from './ErrorBanner'

type Section = 'general' | 'ai' | 'embedding' | 'reranker' | 'models' | 'appearance' | 'server' | 'about'

const SECTIONS: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: 'general', label: '通用', icon: <SettingsIcon size={18} /> },
  { id: 'ai', label: 'AI 模型', icon: <SettingsIcon size={18} /> },
  { id: 'embedding', label: 'Embedding', icon: <SettingsIcon size={18} /> },
  { id: 'reranker', label: 'Reranker', icon: <SettingsIcon size={18} /> },
  { id: 'models', label: '模型管理', icon: <DownloadIcon size={18} /> },
  { id: 'appearance', label: '外观', icon: <SettingsIcon size={18} /> },
  { id: 'server', label: '模型服务', icon: <SettingsIcon size={18} /> },
  { id: 'about', label: '关于', icon: <SettingsIcon size={18} /> },
]

// ---- 按 Provider 分类的模型列表（仅默认值 + 自定义） ----

const EMBED_MODELS: Record<string, { value: string; label: string }[]> = {
  qwen3: [
    { value: 'Qwen/Qwen3-Embedding-0.6B', label: 'Qwen3-Embedding-0.6B' },
  ],
  sentence_transformers: [
    { value: 'BAAI/bge-base-zh-v1.5', label: 'BGE-Base-ZH-v1.5' },
  ],
  openai: [
    { value: 'text-embedding-3-small', label: 'text-embedding-3-small' },
  ],
}

const RERANK_MODELS: Record<string, { value: string; label: string }[]> = {
  qwen3: [
    { value: 'Qwen/Qwen3-Reranker-0.6B', label: 'Qwen3-Reranker-0.6B' },
  ],
  sentence_transformers: [
    { value: 'BAAI/bge-reranker-v2-m3', label: 'BGE-Reranker-v2-M3' },
  ],
}

const LLM_MODELS: Record<string, { value: string; label: string }[]> = {
  openai_compatible: [
    { value: 'Qwen/Qwen2.5-7B-Instruct-GGUF', label: 'Qwen2.5-7B-Instruct' },
  ],
  anthropic: [
    { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4' },
  ],
  ollama: [
    { value: 'qwen2.5:7b', label: 'Qwen2.5-7B' },
  ],
}

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

interface DownloadState {
  [modelId: string]: {
    progress: number
    status: string
    error?: string
    source?: string
    fileName?: string
    fileIndex?: number
    totalFiles?: number
  }
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
  const [customModel, setCustomModel] = useState('')

  // ---- 模型下载状态 ----
  const [models, setModels] = useState<DownloadModel[]>([])
  const [downloadState, setDownloadState] = useState<DownloadState>({})
  const abortRef = useRef<(() => void) | null>(null)

  const loadModels = useCallback(async () => {
    try {
      const resp = await listModels()
      if (resp.success) setModels(resp.models)
    } catch { /* 后端未启动时静默失败 */ }
  }, [])

  useEffect(() => {
    if (open) {
      loadSettings()
      loadModels()
    }
  }, [open, loadModels])

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

  // ---- 模型下载 ----
  const handleDownload = (modelId: string) => {
    if (downloadState[modelId]?.status === 'downloading' || downloadState[modelId]?.status === 'connecting') return

    setDownloadState(prev => ({
      ...prev,
      [modelId]: { progress: 0, status: 'connecting' },
    }))

    abortRef.current = downloadModel(modelId, (event: ProgressEvent) => {
      setDownloadState(prev => {
        const current = prev[modelId] || { progress: 0, status: 'idle' }
        switch (event.status) {
          case 'connecting':
            return { ...prev, [modelId]: { ...current, status: 'connecting', source: event.source } }
          case 'downloading': {
            const progress = event.progress ?? (event.file_progress != null && event.total_files
              ? Math.round(((event.file_index || 1) - 1) * 100 / event.total_files + (event.file_progress || 0) / event.total_files)
              : current.progress)
            return {
              ...prev,
              [modelId]: {
                ...current,
                status: 'downloading',
                progress,
                fileName: event.file,
                fileIndex: event.file_index,
                totalFiles: event.total_files,
              },
            }
          }
          case 'completed':
            loadModels() // 刷新模型列表
            return { ...prev, [modelId]: { progress: 100, status: 'completed', source: event.source } }
          case 'failed':
            return { ...prev, [modelId]: { ...current, status: 'failed', error: event.error } }
          default:
            return prev
        }
      })
    })
  }

  const isModelDownloading = (modelId: string) => {
    const s = downloadState[modelId]
    return s && (s.status === 'connecting' || s.status === 'downloading')
  }

  // ---- 模型选择器组件 ----
  const ModelSelector = ({
    provider,
    modelValue,
    models: modelList,
    onChange,
  }: {
    provider: string
    modelValue: string
    models: Record<string, { value: string; label: string }[]>
    onChange: (v: string) => void
  }) => {
    const options = modelList[provider] || []
    const isKnown = options.some(o => o.value === modelValue) || modelValue === 'custom' || modelValue === ''
    const showCustom = modelValue === 'custom' || (!isKnown && modelValue !== '')

    return (
      <>
        <select
          className="settings-select"
          value={isKnown ? modelValue : 'custom'}
          onChange={e => {
            const v = e.target.value
            if (v === 'custom') {
              onChange(customModel || modelValue)
            } else {
              onChange(v)
              setCustomModel('')
            }
          }}
        >
          {options.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
          <option value="custom">自定义...</option>
        </select>
        {showCustom && (
          <input
            className="settings-input"
            value={isKnown ? customModel : modelValue}
            onChange={e => {
              setCustomModel(e.target.value)
              onChange(e.target.value)
            }}
            placeholder="输入模型名称"
            style={{ marginTop: '8px', maxWidth: '100%' }}
          />
        )}
      </>
    )
  }

  // ---- 进度条组件 ----
  const ProgressBar = ({ modelId }: { modelId: string }) => {
    const state = downloadState[modelId]
    if (!state || state.status === 'idle') return null

    const progress = state.progress || 0

    return (
      <div style={{ marginTop: '8px' }}>
        {state.status === 'connecting' && (
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
            连接中... {state.source && `(${state.source})`}
          </div>
        )}
        {state.status === 'downloading' && (
          <>
            <div className="download-progress">
              <div className="download-progress-bar">
                <div
                  className="download-progress-fill"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <span className="download-progress-text">{progress}%</span>
            </div>
            {state.fileName && (
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                {state.fileName}
                {state.fileIndex && state.totalFiles && ` (${state.fileIndex}/${state.totalFiles})`}
              </div>
            )}
          </>
        )}
        {state.status === 'completed' && (
          <div style={{ fontSize: '12px', color: 'var(--success)' }}>
            下载完成 {state.source && `(来源: ${state.source})`}
          </div>
        )}
        {state.status === 'failed' && (
          <div style={{ fontSize: '12px', color: 'var(--danger)' }}>
            {state.error || '下载失败'}
          </div>
        )}
      </div>
    )
  }

  // ---- 渲染各设置区域 ----
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
                  <div className="setting-desc">选择 LLM 服务提供商</div>
                </div>
                <select
                  className="settings-select"
                  value={settings.llm_provider}
                  onChange={e => {
                    updateSetting('llm_provider', e.target.value)
                    // 切换 provider 时重置 model
                    const models = LLM_MODELS[e.target.value]
                    if (models && models.length > 0) {
                      updateSetting('llm_model', models[0].value)
                    }
                  }}
                >
                  <option value="openai_compatible">OpenAI Compatible</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="ollama">Ollama（本地）</option>
                </select>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Base URL</div>
                  <div className="setting-desc">
                    {settings.llm_provider === 'ollama' ? '默认: http://localhost:11434' : 'API 端点地址'}
                  </div>
                </div>
                <input
                  className="settings-input"
                  value={settings.llm_base_url}
                  onChange={e => updateSetting('llm_base_url', e.target.value)}
                  placeholder={
                    settings.llm_provider === 'ollama'
                      ? 'http://localhost:11434'
                      : 'http://localhost:8000/v1'
                  }
                />
              </div>
              {settings.llm_provider !== 'ollama' && (
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
              )}
              <div className="setting-item" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
                <div className="setting-info">
                  <div className="setting-label">Model</div>
                  <div className="setting-desc">选择或输入模型名称</div>
                </div>
                <ModelSelector
                  provider={settings.llm_provider}
                  modelValue={settings.llm_model}
                  models={LLM_MODELS}
                  onChange={v => updateSetting('llm_model', v)}
                />
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Max Tokens</div>
                  <div className="setting-desc">回复最大 token 数</div>
                </div>
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
                  <div className="setting-desc">本地推理推荐 Qwen3 或 Sentence Transformers</div>
                </div>
                <select
                  className="settings-select"
                  value={settings.embed_provider}
                  onChange={e => {
                    updateSetting('embed_provider', e.target.value)
                    const models = EMBED_MODELS[e.target.value]
                    if (models && models.length > 0) {
                      updateSetting('embed_model', models[0].value)
                    }
                  }}
                >
                  <option value="qwen3">Qwen3（本地）</option>
                  <option value="sentence_transformers">Sentence Transformers（本地）</option>
                  <option value="openai">OpenAI（API）</option>
                </select>
              </div>
              <div className="setting-item" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
                <div className="setting-info">
                  <div className="setting-label">Model</div>
                </div>
                <ModelSelector
                  provider={settings.embed_provider}
                  modelValue={settings.embed_model}
                  models={EMBED_MODELS}
                  onChange={v => updateSetting('embed_model', v)}
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
                  <div className="setting-desc">重排序模型用于提升检索精度</div>
                </div>
                <select
                  className="settings-select"
                  value={settings.rerank_provider}
                  onChange={e => {
                    updateSetting('rerank_provider', e.target.value)
                    const models = RERANK_MODELS[e.target.value]
                    if (models && models.length > 0) {
                      updateSetting('rerank_model', models[0].value)
                    }
                  }}
                >
                  <option value="qwen3">Qwen3（本地）</option>
                  <option value="sentence_transformers">Sentence Transformers（本地）</option>
                </select>
              </div>
              <div className="setting-item" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
                <div className="setting-info">
                  <div className="setting-label">Model</div>
                </div>
                <ModelSelector
                  provider={settings.rerank_provider}
                  modelValue={settings.rerank_model}
                  models={RERANK_MODELS}
                  onChange={v => updateSetting('rerank_model', v)}
                />
              </div>
            </div>
          </div>
        )

      case 'models': {
        const byType = (t: string) => models.filter(m => m.type === t)
        const typeLabels: Record<string, string> = {
          embedding: 'Embedding 模型',
          reranker: 'Reranker 模型',
          detection: '分子检测模型',
        }

        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">下载模型</h3>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px', lineHeight: '1.6' }}>
                下载本地模型以支持 Embedding、Reranker 和分子检测功能。从 ModelScope 下载。
              </p>

              {models.length === 0 ? (
                <div style={{
                  padding: '24px',
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                  fontSize: '13px',
                  background: 'var(--bg-base)',
                  borderRadius: '8px',
                  border: '1px solid var(--border)',
                }}>
                  模型服务未启动，请先启动后端服务
                </div>
              ) : (
                Object.entries(typeLabels).map(([type, label]) => {
                  const group = byType(type)
                  if (group.length === 0) return null
                  return (
                    <div key={type} style={{ marginBottom: '24px' }}>
                      <div style={{
                        fontSize: '12px',
                        fontWeight: 600,
                        color: 'var(--text-secondary)',
                        marginBottom: '8px',
                        padding: '4px 0',
                      }}>
                        {label}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        {group.map(model => {
                          const ds = downloadState[model.id]
                          const downloading = isModelDownloading(model.id)
                          return (
                            <div key={model.id} className="model-card">
                              <div className="model-card-info">
                                <div className="model-card-name">
                                  {model.name}
                                  {model.downloaded && (
                                    <span style={{
                                      marginLeft: '8px',
                                      fontSize: '11px',
                                      color: 'var(--success)',
                                      fontWeight: 400,
                                    }}>
                                      已下载
                                    </span>
                                  )}
                                </div>
                                <div className="model-card-desc">{model.description}</div>
                                {ds && <ProgressBar modelId={model.id} />}
                              </div>
                              <div className="model-card-actions">
                                {!model.downloaded && !downloading && (
                                  <button
                                    className="btn btn-primary"
                                    style={{ padding: '6px 16px', fontSize: '12px' }}
                                    onClick={() => handleDownload(model.id)}
                                  >
                                    下载
                                  </button>
                                )}
                                {downloading && ds?.status === 'downloading' && (
                                  <button
                                    className="btn btn-secondary"
                                    style={{ padding: '6px 16px', fontSize: '12px' }}
                                    onClick={() => {
                                      abortRef.current?.()
                                      setDownloadState(prev => ({
                                        ...prev,
                                        [model.id]: { progress: 0, status: 'idle' },
                                      }))
                                    }}
                                  >
                                    取消
                                  </button>
                                )}
                                {ds?.status === 'completed' && (
                                  <span style={{ fontSize: '12px', color: 'var(--success)' }}>完成</span>
                                )}
                                {ds?.status === 'failed' && (
                                  <button
                                    className="btn btn-secondary"
                                    style={{ padding: '6px 16px', fontSize: '12px' }}
                                    onClick={() => handleDownload(model.id)}
                                  >
                                    重试
                                  </button>
                                )}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                })
              )}

              {/* 自定义模型提示 */}
              <div style={{
                marginTop: '20px',
                padding: '14px 16px',
                background: 'var(--bg-base)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                fontSize: '12px',
                lineHeight: '1.8',
                color: 'var(--text-secondary)',
              }}>
                <div style={{ fontWeight: 600, marginBottom: '6px', color: 'var(--text-primary)' }}>
                  使用其他模型
                </div>
                <div>
                  将模型文件下载到本地目录，然后在对应设置中填入<b>绝对路径</b>即可。
                </div>
                <div style={{ marginTop: '8px', fontFamily: 'monospace', fontSize: '11px', color: 'var(--text-muted)' }}>
                  Embedding / Reranker：直接填本地模型目录路径<br />
                  MolDet：放入 <code>~/.cache/mbforge/models/</code><br />
                  API 模型（OpenAI / Anthropic）：填 Base URL + API Key + 模型名
                </div>
              </div>
            </div>
          </div>
        )
      }

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
                  <div className="setting-desc">0.2.0</div>
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
