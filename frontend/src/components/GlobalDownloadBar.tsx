/** Global model download progress bar — floats below Header. */
import { AnimatePresence, motion } from 'framer-motion'
import { Spinner } from './ui'
import { useTranslation } from 'react-i18next'
import type { DownloadState } from '../hooks/useModelDownloadStatus'

interface Props {
  download: DownloadState
  onDismiss: () => void
}

const STATUS_COLORS: Record<string, string> = {
  connecting: 'var(--info)',
  downloading: 'var(--info)',
  completed: 'var(--success)',
  failed: 'var(--bad)',
}

const STATUS_BG: Record<string, string> = {
  connecting: 'var(--info-muted)',
  downloading: 'var(--info-muted)',
  completed: 'var(--success-muted)',
  failed: 'var(--bad-muted)',
}

function fileLabel(file: string, idx: number, total: number): string {
  if (!file) return ''
  const name = file.split(/[/\\]/).pop() || file
  if (total > 1) return `${name} (${idx + 1}/${total})`
  return name
}

export default function GlobalDownloadBar({ download, onDismiss }: Props) {
  const { t } = useTranslation()
  const visible = download.status !== 'idle'

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key="dlbar"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2 }}
          style={{
            position: 'fixed',
            top: 48,
            left: '50%',
            transform: 'translateX(-50%)',
            minWidth: 360,
            maxWidth: 560,
            padding: '10px 14px',
            background: 'var(--bg-elevated)',
            border: `1px solid ${STATUS_COLORS[download.status] ?? 'var(--border)'}`,
            borderRadius: '10px',
            boxShadow: '0 4px 16px rgba(0,0,0,0.18)',
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            fontSize: '13px',
            color: 'var(--text-primary)',
          }}
        >
          {(download.status === 'connecting' || download.status === 'downloading') && (
            <Spinner size={14} />
          )}
          {download.status === 'completed' && (
            <span style={{ color: 'var(--success)' }}>✓</span>
          )}
          {download.status === 'failed' && (
            <span style={{ color: 'var(--bad)' }}>✕</span>
          )}

          <div style={{ flex: 1, minWidth: 0 }}>
            {download.status === 'connecting' && (
              <div>{t('models.connecting') ?? '连接中…'}</div>
            )}
            {download.status === 'downloading' && (
              <>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginBottom: '4px',
                }}>
                  <span style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    maxWidth: '360px',
                  }}>
                    {fileLabel(download.file, download.fileIndex, download.totalFiles)}
                  </span>
                  <span style={{ color: 'var(--text-muted)', flexShrink: 0, marginLeft: 8 }}>
                    {Math.round(download.fileProgress * 100)}%
                  </span>
                </div>
                <div style={{
                  height: '4px',
                  background: STATUS_BG[download.status],
                  borderRadius: '2px',
                  overflow: 'hidden',
                }}>
                  <motion.div
                    initial={false}
                    animate={{ width: `${Math.round(download.fileProgress * 100)}%` }}
                    transition={{ duration: 0.3 }}
                    style={{
                      height: '100%',
                      background: STATUS_COLORS[download.status],
                    }}
                  />
                </div>
              </>
            )}
            {download.status === 'completed' && (
              <div style={{ color: 'var(--success)' }}>
                {t('models.downloadComplete') ?? '下载完成'}
              </div>
            )}
            {download.status === 'failed' && (
              <div style={{ color: 'var(--bad)' }}>
                {download.error || (t('models.downloadFailed') ?? '下载失败')}
              </div>
            )}
          </div>

          {(download.status === 'completed' || download.status === 'failed') && (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="close"
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--text-muted)',
                fontSize: '16px',
                padding: 0,
                lineHeight: 1,
              }}
            >
              ✕
            </button>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
