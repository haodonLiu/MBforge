import { useState, useCallback, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import Button from '../ui/Button'
import {
  listModels,
  listDownloaded,
  downloadModel,
  deleteModel,
  type DownloadModel,
  type DownloadedModel,
  type DownloadProgress,
} from '../../api/tauri/download'
import ModelCard from './ModelCard'
import DownloadedModelItem from './DownloadedModelItem'

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

export default function ModelsTab() {
  const { t } = useTranslation()
  const [models, setModels] = useState<DownloadModel[]>([])
  const [downloadedModels, setDownloadedModels] = useState<DownloadedModel[]>([])
  const [modelDir, setModelDir] = useState('')
  const [downloadState, setDownloadState] = useState<DownloadState>({})
  const [modelTab, setModelTab] = useState<'catalog' | 'downloaded'>('catalog')
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const abortMapRef = useRef<Map<string, () => void>>(new Map())

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

  useEffect(() => {
    loadModels()
    loadDownloaded()
  }, [loadModels, loadDownloaded])

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
      loadDownloaded()
      loadModels()
    } catch (e) {
      console.error(e)
    }
  }

  const byType = (type_: string) => models.filter(m => m.type === type_)
  const typeLabels: Record<string, string> = {
    embedding: t('models.embedding'),
    reranker: t('models.reranker'),
    detection: t('models.detection'),
  }

  return (
    <div className="settings-section">
      <div className="settings-group">
        <div className="settings-tabs-row">
          <Button
            size="sm"
            className={modelTab === 'catalog' ? 'settings-tab-btn--active' : ''}
            onClick={() => setModelTab('catalog')}
          >
            {t('models.tabCatalog')}
          </Button>
          <Button
            size="sm"
            className={modelTab === 'downloaded' ? 'settings-tab-btn--active' : ''}
            onClick={() => { setModelTab('downloaded'); loadDownloaded() }}
          >
            {t('models.tabDownloaded', { count: downloadedModels.length })}
          </Button>
        </div>

        <div className="settings-model-dir">
          <span className="settings-model-dir-label">{t('models.modelDir')}</span>
          <code className="settings-model-dir-path">
            {modelDir || '~/.cache/mbforge/models/'}
          </code>
        </div>

        {modelTab === 'catalog' ? (
          models.length === 0 ? (
            <div className="settings-empty-state">
              {t('models.serverNotStarted')}
            </div>
          ) : (
            Object.entries(typeLabels).map(([type, label]) => {
              const group = byType(type)
              if (group.length === 0) return null
              return (
                <div key={type} className="settings-model-group">
                  <div className="settings-model-group-label">{label}</div>
                  <div className="settings-model-list">
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
          downloadedModels.length === 0 ? (
            <div className="settings-empty-state">
              {t('models.noDownloaded')}
            </div>
          ) : (
            <div className="settings-model-list">
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

        <div className="settings-custom-hint">
          <div className="settings-custom-hint-title">{t('models.customTitle')}</div>
          <div>{t('models.customDesc')}</div>
          <div className="settings-custom-hint-code">{t('models.customHint')}</div>
        </div>
      </div>
    </div>
  )
}
