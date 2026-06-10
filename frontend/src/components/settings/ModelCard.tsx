import { useTranslation } from 'react-i18next'
import Button from '../ui/Button'
import type { DownloadModel } from '../../api/tauri/download'
import type { DownloadState } from './ModelsTab'
import ProgressBar from './ProgressBar'

interface ModelCardProps {
  model: DownloadModel
  state?: DownloadState[string]
  onDownload: () => void
  onCancel: () => void
}

export default function ModelCard({ model, state, onDownload, onCancel }: ModelCardProps) {
  const { t } = useTranslation()
  const isDownloading = state && (state.status === 'connecting' || state.status === 'downloading')

  return (
    <div className="model-card">
      <div className="model-card-info">
        <div className="model-card-name">
          {model.name}
          {model.downloaded && <span className="model-card-badge model-card-badge--success">{t('models.downloaded')}</span>}
          {model.license && (
            <a href={model.license_url || '#'} target="_blank" rel="noopener noreferrer" className="model-card-license">
              {model.license}
            </a>
          )}
          {model.size_mb > 0 && <span className="model-card-size">~{model.size_mb}MB</span>}
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
        {state?.status === 'completed' && <span className="model-card-done">{t('models.done')}</span>}
        {state?.status === 'failed' && (
          <Button size="sm" variant="secondary" onClick={onDownload}>{t('models.retry')}</Button>
        )}
      </div>
    </div>
  )
}
