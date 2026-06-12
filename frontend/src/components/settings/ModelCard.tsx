import { useTranslation } from 'react-i18next'
import Button from '../ui/Button'
import type { DownloadModel } from '../../api/tauri/download'
import type { DownloadState } from './ModelsTab'
import ProgressBar from './ProgressBar'

interface ModelCardProps {
  model: DownloadModel
  state?: DownloadState[string]
  deleteConfirm?: string | null
  onDownload: () => void
  onCancel: () => void
  onDelete: () => void
  onConfirmDelete: () => void
  onCancelDelete: () => void
}

export default function ModelCard({
  model,
  state,
  deleteConfirm,
  onDownload,
  onCancel,
  onDelete,
  onConfirmDelete,
  onCancelDelete,
}: ModelCardProps) {
  const { t } = useTranslation()
  const isDownloading = state && (state.status === 'connecting' || state.status === 'downloading')
  const isConfirmingDelete = deleteConfirm === model.id

  return (
    <div className="model-card">
      <div className="model-card-info">
        <div className="model-card-name">
          <span className="model-card-title">{model.name}</span>
          {model.downloaded && (
            <span className="model-card-badge model-card-badge--success">{t('models.downloaded')}</span>
          )}
          {isDownloading && (
            <span className="model-card-badge model-card-badge--active">{t('models.downloading')}</span>
          )}
          {model.size_mb > 0 && <span className="model-card-size">~{model.size_mb < 1024 ? `${model.size_mb} MB` : `${(model.size_mb / 1024).toFixed(1)} GB`}</span>}
        </div>
        <div className="model-card-desc">{model.description}</div>
        {model.downloaded && model.local_path && (
          <div className="model-card-path" title={model.local_path}>
            {model.local_path}
          </div>
        )}
        {state && state.status !== 'idle' && <ProgressBar state={state} />}
      </div>
      <div className="model-card-actions">
        {!model.downloaded && !isDownloading && (
          <Button size="sm" variant="primary" onClick={onDownload}>{t('models.download')}</Button>
        )}
        {isDownloading && (
          <Button size="sm" variant="secondary" onClick={onCancel}>{t('models.cancel')}</Button>
        )}
        {model.downloaded && !isDownloading && !isConfirmingDelete && (
          <Button size="sm" variant="secondary" onClick={onDelete}>{t('models.delete')}</Button>
        )}
        {isConfirmingDelete && (
          <div className="model-card-confirm">
            <span className="model-card-confirm-text">{t('models.confirmDelete')}</span>
            <Button size="sm" variant="secondary" onClick={onCancelDelete}>{t('models.cancel')}</Button>
            <Button size="sm" variant="danger" onClick={onConfirmDelete}>{t('models.delete')}</Button>
          </div>
        )}
        {state?.status === 'completed' && <span className="model-card-done">{t('models.done')}</span>}
        {state?.status === 'failed' && (
          <Button size="sm" variant="secondary" onClick={onDownload}>{t('models.retry')}</Button>
        )}
      </div>
    </div>
  )
}
