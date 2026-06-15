/** Container for GlobalDownloadBar — owns dismiss state. */
import { useCallback, useState } from 'react'
import GlobalDownloadBar from './GlobalDownloadBar'
import { useModelDownloadStatus } from '../hooks/useModelDownloadStatus'

export default function GlobalDownloadBarHost() {
  const { download: rawDownload } = useModelDownloadStatus()
  const [dismissed, setDismissed] = useState(false)

  // 当一次下载重新开始时（status 从 idle 变为 connecting），清掉 dismissed
  const download = dismissed && rawDownload.status !== 'idle' && rawDownload.status !== 'completed' && rawDownload.status !== 'failed'
    ? (() => { setDismissed(false); return rawDownload })()
    : rawDownload

  const onDismiss = useCallback(() => setDismissed(true), [])

  // 显式 completed/failed 且已 dismiss → 不展示
  if (dismissed && (rawDownload.status === 'completed' || rawDownload.status === 'failed')) {
    return null
  }

  return <GlobalDownloadBar download={download} onDismiss={onDismiss} />
}
