import { useTranslation } from 'react-i18next'
import { TrashIcon } from '../icons'
import type { DownloadedModel } from '../../api/tauri/download'

interface DownloadedModelItemProps {
  model: DownloadedModel
  deleteConfirm: string | null
  onDeleteClick: () => void
  onConfirmDelete: () => void
  onCancelDelete: () => void
}

export default function DownloadedModelItem({
  model,
  deleteConfirm,
  onDeleteClick,
  onConfirmDelete,
  onCancelDelete,
}: DownloadedModelItemProps) {
  const { t } = useTranslation()
  return (
    <div className="settings-downloaded-item">
      <div className="settings-downloaded-info">
        <div className="settings-downloaded-name">
          <span>{model.name}</span>
          <span className="settings-downloaded-size">{model.size_mb > 0 ? `${model.size_mb} MB` : ''}</span>
          {model.in_catalog && <span className="settings-downloaded-badge">{t('models.official')}</span>}
        </div>
        <div className="settings-downloaded-path">{model.path}</div>
      </div>
      <div className="settings-downloaded-actions">
        {deleteConfirm === model.id ? (
          <>
            <span className="settings-downloaded-confirm-text">{t('models.confirmDelete')}</span>
            <button className="settings-downloaded-btn settings-downloaded-btn--secondary" onClick={onCancelDelete}>{t('models.cancel')}</button>
            <button className="settings-downloaded-btn settings-downloaded-btn--danger" onClick={onConfirmDelete}>{t('models.delete')}</button>
          </>
        ) : (
          <button className="settings-downloaded-btn settings-downloaded-btn--delete" onClick={onDeleteClick}>
            <TrashIcon size={12} /> {t('models.delete')}
          </button>
        )}
      </div>
    </div>
  )
}
