import { useTranslation } from 'react-i18next'
import Button from '@/components/ui/Button'
import type { DownloadModel, SubfileStatus } from '../../api/http/download'
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
  onDownloadSubfile?: (subpath: string) => void
  onTest?: (subpath?: string) => void
  subfileStates?: Record<string, DownloadState[string]>
  testingSubfiles?: Set<string>
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
  onDownloadSubfile,
  onTest,
  subfileStates,
  testingSubfiles,
}: ModelCardProps) {
  const { t } = useTranslation()
  const isDownloading = state && (state.status === 'connecting' || state.status === 'downloading')
  const isConfirmingDelete = deleteConfirm === model.id
  const hasSubfiles = model.subfiles && model.subfiles.length > 0
  const readySubCount = hasSubfiles ? model.subfiles.filter(s => s.ready).length : 0
  const allReady = hasSubfiles ? readySubCount === model.subfiles.length : model.downloaded
  // 卡片级 Test 在跑：单文件看 testingSubfiles 是否包含 `${id}::`；多文件也按同样 key
  const isTesting = testingSubfiles !== undefined && testingSubfiles.size > 0

  return (
    <div className="model-card">
      <div className="model-card-info">
        <div className="model-card-name">
          <span className={`model-card-status ${allReady ? 'model-card-status--ready' : 'model-card-status--missing'}`}>
            {allReady ? '✓' : '✗'}
          </span>
          <span className="model-card-title">{model.name}</span>
          {hasSubfiles && (
            <span className="model-card-size">
              {readySubCount} / {model.subfiles.length} {t('models.subfileSuffix')}
            </span>
          )}
          {!hasSubfiles && allReady && (
            <span className="model-card-badge model-card-badge--success">{t('models.downloaded')}</span>
          )}
          {isDownloading && (
            <span className="model-card-badge model-card-badge--active">{t('models.downloading')}</span>
          )}
          {!hasSubfiles && model.size_mb > 0 && (
            <span className="model-card-size">~{model.size_mb < 1024 ? `${model.size_mb} MB` : `${(model.size_mb / 1024).toFixed(1)} GB`}</span>
          )}
        </div>
        <div className="model-card-desc">{model.description}</div>
        {/* 单文件资源：显示期望/已就位路径 */}
        {!hasSubfiles && model.expected_path && (
          <div className="model-card-expected" title={model.expected_path}>
            {allReady
              ? t('models.foundAt', { path: model.expected_path })
              : t('models.expectedAt', { path: model.expected_path })}
          </div>
        )}
        {state && state.status !== 'idle' && !hasSubfiles && <ProgressBar state={state} />}

        {/* 多文件资源：每个子文件只暴露 Download（完成后按钮隐藏） */}
        {hasSubfiles && (
          <div className="model-card-subfiles">
            {model.subfiles.map(sf => (
              <SubfileRow
                key={sf.relpath}
                subfile={sf}
                downloadState={subfileStates?.[sf.relpath]}
                onDownload={!sf.ready && onDownloadSubfile ? () => onDownloadSubfile(sf.relpath) : undefined}
              />
            ))}
          </div>
        )}
      </div>

      {/* 卡片级操作（所有模型都有）：Test + Delete(+ 必要时 Download/Cancel) */}
      <div className="model-card-actions">
        {/* 多文件未全部就绪：单文件下载已不需要（单文件 download 按钮在子行/无），但单文件模型可能 missing */}
        {!hasSubfiles && !allReady && !isDownloading && (
          <Button size="sm" variant="primary" onClick={onDownload}>{t('models.download')}</Button>
        )}
        {isDownloading && (
          <Button size="sm" variant="secondary" onClick={onCancel}>{t('models.cancel')}</Button>
        )}
        {/* Test：单文件 ready / 多文件全部 ready 时显示 */}
        {allReady && !isDownloading && !isConfirmingDelete && onTest && (
          <Button size="sm" variant="secondary" onClick={() => onTest()} disabled={isTesting}>
            {isTesting ? `⟳ ${t('models.testing')}` : t('models.test')}
          </Button>
        )}
        {/* Delete：单文件 ready / 多文件至少 1 个 ready 时显示 */}
        {(allReady || (hasSubfiles && readySubCount > 0)) && !isDownloading && !isConfirmingDelete && (
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
        {state?.status === 'failed' && !hasSubfiles && (
          <Button size="sm" variant="secondary" onClick={onDownload}>{t('models.retry')}</Button>
        )}
      </div>
    </div>
  )
}

interface SubfileRowProps {
  subfile: SubfileStatus
  downloadState?: DownloadState[string]
  /** 已就绪时为 undefined → 按钮隐藏 */
  onDownload?: () => void
}

function SubfileRow({ subfile, downloadState, onDownload }: SubfileRowProps) {
  const { t } = useTranslation()
  const isDownloading = downloadState && (downloadState.status === 'connecting' || downloadState.status === 'downloading')

  return (
    <div className="subfile-row">
      <span className={`subfile-row-status ${subfile.ready ? 'subfile-row-status--ready' : 'subfile-row-status--missing'}`}>
        {subfile.ready ? '✓' : '✗'}
      </span>
      <div className="subfile-row-info">
        <div className="subfile-row-label" title={subfile.local_path}>
          {subfile.label}
        </div>
        {downloadState && downloadState.status !== 'idle' && <ProgressBar state={downloadState} />}
      </div>
      <div className="subfile-row-actions">
        {!subfile.ready && !isDownloading && onDownload && (
          <Button size="sm" variant="primary" onClick={onDownload}>{t('models.download')}</Button>
        )}
        {isDownloading && (
          <span className="subfile-row-progress">{t('models.downloading')}…</span>
        )}
      </div>
    </div>
  )
}
