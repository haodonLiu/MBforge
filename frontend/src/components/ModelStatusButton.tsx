/** Sidebar 模型状态按钮 — 状态点 + 点击跳转到 Settings 页。 */
import { useNavigate } from 'react-router-dom'
import { Tooltip } from './ui'
import IconButton from './ui/IconButton'
import { FlaskIcon } from './icons/science'
import { useModelDownloadStatus, type ModelStatus } from '../hooks/useModelDownloadStatus'

const STATUS_COLOR: Record<ModelStatus, string> = {
  ready: 'var(--success)',
  downloading: 'var(--warning)',
  missing: 'var(--bad)',
  failed: 'var(--bad)',
  unknown: 'var(--text-muted)',
}

const STATUS_LABEL: Record<ModelStatus, string> = {
  ready: '模型已就绪',
  downloading: '正在下载模型',
  missing: '有模型待下载',
  failed: '模型下载失败',
  unknown: '检测模型状态…',
}

interface Props {
  projectRoot: string
}

export default function ModelStatusButton({ projectRoot }: Props) {
  const navigate = useNavigate()
  const { snapshot } = useModelDownloadStatus()

  // 未打开项目时不展示该按钮（Welcome 阶段无意义）
  if (!projectRoot) return null

  const color = STATUS_COLOR[snapshot.status]
  const label = STATUS_LABEL[snapshot.status]
  const detail = snapshot.missing > 0
    ? `${label} (${snapshot.total - snapshot.missing}/${snapshot.total} 已下载)`
    : label

  return (
    <Tooltip text={detail}>
      <div style={{ position: 'relative' }}>
        <IconButton onClick={() => void navigate('/settings')}>
          <FlaskIcon size={20} />
        </IconButton>
        <span
          aria-label={label}
          style={{
            position: 'absolute',
            top: '4px',
            right: '4px',
            width: '10px',
            height: '10px',
            borderRadius: '50%',
            background: color,
            boxShadow: '0 0 0 2px var(--bg-surface)',
          }}
        />
      </div>
    </Tooltip>
  )
}
