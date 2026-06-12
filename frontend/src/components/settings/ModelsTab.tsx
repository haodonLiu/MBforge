import { useState, useCallback, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  listModels,
  downloadModel,
  deleteModel,
  type DownloadModel,
  type DownloadProgress,
} from '../../api/tauri/download'
import { invoke } from '@tauri-apps/api/core'
import ModelCard from './ModelCard'

export interface DownloadState {
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

interface ModelsTabProps {
  modelCacheDir: string
  onCacheDirChange: (v: string) => void
}

export default function ModelsTab({ modelCacheDir, onCacheDirChange }: ModelsTabProps) {
  const { t } = useTranslation()
  const [models, setModels] = useState<DownloadModel[]>([])
  const [downloadState, setDownloadState] = useState<DownloadState>({})
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [customOpen, setCustomOpen] = useState(false)
  const [cacheDir, setCacheDir] = useState('')
  const abortMapRef = useRef<Map<string, () => void>>(new Map())

  const loadModels = useCallback(async () => {
    try {
      const resp = await listModels()
      if (resp.success) setModels(resp.models)
    } catch { /* 后端未启动时静默失败 */ }
  }, [])

  const loadCacheDir = useCallback(async () => {
    try {
      const info = await invoke<{ mbforge: { path: string } }>('models_cache_dir_info')
      setCacheDir(info.mbforge?.path ?? '')
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    loadModels()
    loadCacheDir()
  }, [loadModels, loadCacheDir])

  const handleDownload = (modelId: string) => {
    if (downloadState[modelId]?.status === 'downloading' || downloadState[modelId]?.status === 'connecting') return

    setDownloadState(prev => ({
      ...prev,
      [modelId]: { progress: 0, status: 'connecting' },
    }))

    const cleanup = downloadModel(modelId, (event: DownloadProgress) => {
      setDownloadState(prev => {
        const current = prev[modelId] || { progress: 0, status: 'idle' }
        switch (event.status) {
          case 'connecting':
            return { ...prev, [modelId]: { ...current, status: 'connecting' } }
          case 'downloading': {
            const progress = event.total_files > 0
              ? Math.round(((event.file_index) * 100 / event.total_files) + (event.file_progress * 100 / event.total_files))
              : current.progress
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
            return { ...prev, [modelId]: { progress: 100, status: 'completed' } }
          case 'failed':
            return { ...prev, [modelId]: { ...current, status: 'failed', error: event.error } }
          default:
            return prev
        }
      })
    })
    abortMapRef.current.set(modelId, cleanup)
  }

  const handleCancel = (modelId: string) => {
    abortMapRef.current.get(modelId)?.()
    abortMapRef.current.delete(modelId)
    setDownloadState(prev => ({ ...prev, [modelId]: { progress: 0, status: 'idle' } }))
  }

  const handleDelete = async (modelId: string) => {
    try {
      await deleteModel(modelId)
      setDeleteConfirm(null)
      loadModels()
    } catch (e) {
      console.error(e)
    }
  }

  // 按 type 分组（保持顺序：embedding → reranker → detection）
  const typeOrder: Array<{ key: string; labelKey: string }> = [
    { key: 'embedding', labelKey: 'models.embedding' },
    { key: 'reranker', labelKey: 'models.reranker' },
    { key: 'detection', labelKey: 'models.detection' },
  ]

  const readyCount = models.filter(m => m.downloaded).length
  const totalCount = models.length

  return (
    <div className="settings-section">
      <div className="settings-group">
        {/* 摘要头部 */}
        <div className="models-header">
          <div className="models-header-summary">
            <span className="models-header-count">
              {t('models.readyCount', { ready: readyCount, total: totalCount })}
            </span>
            {cacheDir && (
              <code className="models-header-dir" title={cacheDir}>
                {cacheDir}
              </code>
            )}
            <input
              className="models-header-dir-input"
              type="text"
              value={modelCacheDir}
              onChange={e => onCacheDirChange(e.target.value)}
              placeholder={t('settings.modelCacheDirPlaceholder')}
              spellCheck={false}
            />
          </div>
          <button className="models-header-refresh" onClick={loadModels} title={t('models.refresh')}>
            ↻ {t('models.refresh')}
          </button>
        </div>

        {models.length === 0 ? (
          <div className="settings-empty-state">
            {t('models.serverNotStarted')}
          </div>
        ) : (
          typeOrder.map(({ key, labelKey }) => {
            const group = models.filter(m => m.type === key)
            if (group.length === 0) return null
            const groupReady = group.filter(m => m.downloaded).length
            return (
              <div key={key} className="settings-model-group">
                <div className="settings-model-group-label">
                  <span>{t(labelKey)}</span>
                  <span className="settings-model-group-count">{groupReady} / {group.length}</span>
                </div>
                <div className="settings-model-list">
                  {group.map(model => (
                    <ModelCard
                      key={model.id}
                      model={model}
                      state={downloadState[model.id]}
                      deleteConfirm={deleteConfirm}
                      onDownload={() => handleDownload(model.id)}
                      onCancel={() => handleCancel(model.id)}
                      onDelete={() => setDeleteConfirm(model.id)}
                      onConfirmDelete={() => handleDelete(model.id)}
                      onCancelDelete={() => setDeleteConfirm(null)}
                    />
                  ))}
                </div>
              </div>
            )
          })
        )}

        {/* 自定义模型提示（可折叠） */}
        <details className="settings-custom-hint" open={customOpen} onToggle={e => setCustomOpen((e.target as HTMLDetailsElement).open)}>
          <summary className="settings-custom-hint-title">{t('models.customTitle')}</summary>
          <div className="settings-custom-hint-body">
            <div>{t('models.customDesc')}</div>
            <div className="settings-custom-hint-code">{t('models.customHint')}</div>
          </div>
        </details>
      </div>
    </div>
  )
}
