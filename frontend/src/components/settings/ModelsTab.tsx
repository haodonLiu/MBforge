import { useState, useCallback } from 'react'
import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import Button from '../ui/Button'
import { listModels, downloadModel, listDownloaded, deleteModel, type DownloadModel, type DownloadedModel, type ProgressEvent } from '../../api/download'

// ============ Types ============
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

// ============ Progress Bar ============
function ProgressBar({ state }: { state: DownloadState[string] }) {
  const { t } = useTranslation()
  if (!state || state.status === 'idle') return null
  const progress = state.progress || 0

  return (
    <div style={{ marginTop: '8px' }}>
      {state.status === 'connecting' && (
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          {t('models.downloading')} {state.source && t('models.fromSource', { source: state.source })}
        </span>
      )}
      {state.status === 'downloading' && (
        <>
          <div className="download-progress">
            <div className="download-progress-bar">
              <div className="download-progress-fill" style={{ width: `${progress}%` }} />
            </div>
            <span className="download-progress-text">{progress}%</span>
          </div>
          {state.fileName && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: '4px' }}>
              {state.fileName}
              {state.fileIndex && state.totalFiles && ` (${state.fileIndex}/${state.totalFiles})`}
            </div>
          )}
        </>
      )}
      {state.status === 'completed' && (
        <span style={{ fontSize: 11, color: 'var(--success)' }}>
          {t('models.downloadComplete')} {state.source && t('models.fromSource', { source: state.source })}
        </span>
      )}
      {state.status === 'failed' && (
        <span style={{ fontSize: 11, color: 'var(--danger)' }}>
          {state.error || t('models.downloadFailed')}
        </span>
      )}
    </div>
  )
}

// ============ Model Card ============
function ModelCard({
  model,
  state,
  onDownload,
  onCancel,
}: {
  model: DownloadModel
  state?: DownloadState[string]
  onDownload: () => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const isDownloading = state && (state.status === 'connecting' || state.status === 'downloading')

  return (
    <div className="model-card">
      <div className="model-card-info">
        <div className="model-card-name">
          {model.name}
          {model.downloaded && (
            <span style={{ marginLeft: '8px', fontSize: 10, padding: '1px 6px', background: 'var(--success)', color: 'white', borderRadius: 4 }}>{t('models.downloaded')}</span>
          )}
          {model.license && (
            <a href={model.license_url || '#'} target="_blank" rel="noopener noreferrer" style={{ marginLeft: '8px', fontSize: 10, color: 'var(--text-muted)' }}>
              {model.license}
            </a>
          )}
          {model.size_mb > 0 && (
            <span style={{ marginLeft: '8px', fontSize: 10, color: 'var(--text-muted)' }}>~{model.size_mb}MB</span>
          )}
        </div>
        <div className="model-card-desc">{model.description}</div>
        {state && state.status !== 'idle' && <ProgressBar state={state} />}
      </div>
      <div className="model-card-actions">
        {!model.downloaded && !isDownloading && (
          <Button size="sm" variant="primary" onClick={onDownload}>{t('models.download')}</Button>
        )}
        {isDownloading && (
          <Button size="sm" variant="secondary" onClick={onCancel}>{t('models.cancel')}</Button>
        )}
        {state?.status === 'completed' && <span style={{ fontSize: 11, color: 'var(--success)' }}>{t('models.done')}</span>}
        {state?.status === 'failed' && (
          <Button size="sm" variant="secondary" onClick={onDownload}>{t('models.retry')}</Button>
        )}
      </div>
    </div>
  )
}

// ============ Downloaded Model Item ============
import { TrashIcon } from '../icons'

function DownloadedModelItem({
  model,
  deleteConfirm,
  onDeleteClick,
  onConfirmDelete,
  onCancelDelete,
}: {
  model: DownloadedModel
  deleteConfirm: string | null
  onDeleteClick: () => void
  onConfirmDelete: () => void
  onCancelDelete: () => void
}) {
  const { t } = useTranslation()
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '12px 14px',
      background: 'var(--bg-base)',
      border: '1px solid var(--border)',
      borderRadius: '8px',
      gap: '12px',
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>{model.name}</span>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{model.size_mb > 0 ? `${model.size_mb} MB` : ''}</span>
          {model.in_catalog && (
            <span style={{ fontSize: 10, color: 'var(--success)', background: 'rgba(34,197,94,0.1)', padding: '1px 6px', borderRadius: 4 }}>官方</span>
          )}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace', wordBreak: 'break-all', marginTop: 2 }}>{model.path}</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        {deleteConfirm === model.id ? (
          <>
            <span style={{ fontSize: 11, color: 'var(--danger)' }}>{t('models.confirmDelete')}</span>
            <button className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: 11 }} onClick={onCancelDelete}>{t('models.cancel')}</button>
            <button className="btn btn-primary" style={{ padding: '4px 10px', fontSize: 11, background: 'var(--danger)' }} onClick={onConfirmDelete}>{t('models.delete')}</button>
          </>
        ) : (
          <button className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: 11, color: 'var(--danger)' }} onClick={onDeleteClick}>
            <TrashIcon size={12} /> {t('models.delete')}
          </button>
        )}
      </div>
    </div>
  )
}

// ============ Main Component ============
export default function ModelsTab() {
  const { t } = useTranslation()
  const [models, setModels] = useState<DownloadModel[]>([])
  const [downloadedModels, setDownloadedModels] = useState<DownloadedModel[]>([])
  const [modelDir, setModelDir] = useState('')
  const [downloadState, setDownloadState] = useState<DownloadState>({})
  const [modelTab, setModelTab] = useState<'catalog' | 'downloaded'>('catalog')
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const abortRef = useRef<(() => void) | null>(null)

  // Load models
  const loadModels = useCallback(async () => {
    try {
      const resp = await listModels()
      if (resp.success) setModels(resp.models)
    } catch { /* 后端未启动时静默失败 */ }
  }, [])

  const loadDownloaded = useCallback(async () => {
    try {
      const resp = await listDownloaded()
      if (resp.success) {
        setDownloadedModels(resp.models)
        setModelDir(resp.model_dir)
      }
    } catch { /* 后端未启动时静默失败 */ }
  }, [])

  // Load on mount
  useState(() => {
    loadModels()
    loadDownloaded()
  })

  // Download handler
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
            loadModels()
            return { ...prev, [modelId]: { progress: 100, status: 'completed', source: event.source } }
          case 'failed':
            return { ...prev, [modelId]: { ...current, status: 'failed', error: event.error } }
          default:
            return prev
        }
      })
    })
  }

  const handleCancel = (modelId: string) => {
    abortRef.current?.()
    setDownloadState(prev => ({ ...prev, [modelId]: { progress: 0, status: 'idle' } }))
  }

  // Delete handler
  const handleDelete = async (modelId: string) => {
    try {
      const resp = await deleteModel(modelId)
      if (resp.success) {
        setDeleteConfirm(null)
        loadDownloaded()
        loadModels()
      }
    } catch (e) {
      console.error(e)
    }
  }

  // Group models by type
  const byType = (type_: string) => models.filter(m => m.type === type_)
  const typeLabels: Record<string, string> = {
    embedding: t('models.embedding'),
    reranker: t('models.reranker'),
    detection: t('models.detection'),
  }

  return (
    <div className="settings-section">
      <div className="settings-group">
        {/* Tab 切换 */}
        <div style={{ display: 'flex', gap: '4px', marginBottom: '16px' }}>
          <Button
            size="sm"
            style={{
              padding: '6px 14px',
              background: modelTab === 'catalog' ? 'var(--accent-muted)' : undefined,
              color: modelTab === 'catalog' ? 'var(--accent)' : undefined,
            }}
            onClick={() => setModelTab('catalog')}
          >
            {t('models.tabCatalog')}
          </Button>
          <Button
            size="sm"
            style={{
              padding: '6px 14px',
              background: modelTab === 'downloaded' ? 'var(--accent-muted)' : undefined,
              color: modelTab === 'downloaded' ? 'var(--accent)' : undefined,
            }}
            onClick={() => { setModelTab('downloaded'); loadDownloaded() }}
          >
            {t('models.tabDownloaded', { count: downloadedModels.length })}
          </Button>
        </div>

        {/* 模型目录信息 */}
        <div style={{
          padding: '10px 14px',
          background: 'var(--bg-base)',
          border: '1px solid var(--border)',
          borderRadius: '8px',
          fontSize: 12,
          marginBottom: '16px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          <span style={{ color: 'var(--text-muted)' }}>{t('models.modelDir')}</span>
          <code style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
            {modelDir || '~/.cache/mbforge/models/'}
          </code>
        </div>

        {modelTab === 'catalog' ? (
          /* 可用模型列表 */
          models.length === 0 ? (
            <div style={{
              padding: 24,
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: 13,
              background: 'var(--bg-base)',
              borderRadius: 8,
              border: '1px solid var(--border)',
            }}>
              {t('models.serverNotStarted')}
            </div>
          ) : (
            Object.entries(typeLabels).map(([type, label]) => {
              const group = byType(type)
              if (group.length === 0) return null
              return (
                <div key={type} style={{ marginBottom: 24 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8, padding: '4px 0' }}>
                    {label}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {group.map(model => (
                      <ModelCard
                        key={model.id}
                        model={model}
                        state={downloadState[model.id]}
                        onDownload={() => handleDownload(model.id)}
                        onCancel={() => handleCancel(model.id)}
                      />
                    ))}
                  </div>
                </div>
              )
            })
          )
        ) : (
          /* 已下载模型列表 */
          downloadedModels.length === 0 ? (
            <div style={{
              padding: 24,
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: 13,
              background: 'var(--bg-base)',
              borderRadius: 8,
              border: '1px solid var(--border)',
            }}>
              {t('models.noDownloaded')}
             </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {downloadedModels.map(model => (
                <DownloadedModelItem
                  key={model.id}
                  model={model}
                  deleteConfirm={deleteConfirm}
                  onDeleteClick={() => setDeleteConfirm(model.id)}
                  onConfirmDelete={() => handleDelete(model.id)}
                  onCancelDelete={() => setDeleteConfirm(null)}
                />
              ))}
            </div>
          )
        )}

        {/* 自定义模型提示 */}
        <div style={{
          marginTop: 20,
          padding: '14px 16px',
          background: 'var(--bg-base)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          fontSize: 12,
          lineHeight: 1.8,
          color: 'var(--text-secondary)',
        }}>
          <div style={{ fontWeight: 600, marginBottom: 6, color: 'var(--text-primary)' }}>
            {t('models.customTitle')}
          </div>
          <div>{t('models.customDesc')}</div>
          <div style={{ marginTop: 8, fontFamily: 'monospace', fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'pre-line' }}>
            {t('models.customHint')}
          </div>
        </div>
      </div>
    </div>
  )
}
