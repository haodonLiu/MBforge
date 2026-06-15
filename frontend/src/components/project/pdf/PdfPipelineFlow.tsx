import type { FC } from 'react'
import { TargetIcon } from '../../icons/science'
import { FileTextIcon } from '../../icons/nav'
import { EyeIcon, CheckIcon, XIcon } from '../../icons/actions'
import { FlaskIcon, NetworkIcon, EmbedIcon } from '../../icons/science'
import type { IngestTask } from '../../../api/tauri/ingest_queue'
import ProgressBar from '../../ui/ProgressBar'
import '../../../styles/pdf-pipeline-flow.css'

type PipelineVariant = 'compact' | 'full'

export type EmbedSubState = {
  action: 'start' | 'done' | 'failed' | 'skipped'
  model: string
  progress: number
}

interface PdfPipelineFlowProps {
  variant: PipelineVariant
  task: IngestTask | null
  progressPct?: number
  details?: string
  /** Track C: 嵌入子阶段状态（index 阶段内） */
  embedState?: EmbedSubState | null
}

const STAGES: { key: string; label: string; Icon: FC<{ size?: number }> }[] = [
  { key: 'inspector', label: '文档检测', Icon: TargetIcon },
  { key: 'text_extract', label: '文本提取', Icon: FileTextIcon },
  { key: 'ocr', label: 'OCR', Icon: EyeIcon },
  { key: 'moldet', label: '分子扫描', Icon: FlaskIcon },
  { key: 'embed', label: '嵌入', Icon: EmbedIcon },
  { key: 'index', label: '索引构建', Icon: NetworkIcon },
]

type NodeState = 'idle' | 'running' | 'done' | 'failed' | 'skipped'

function getNodeStates(
  task: IngestTask,
  embedState?: EmbedSubState | null,
): NodeState[] {
  // Track C: 嵌入在 index 阶段内串行；用 embedState 决定"嵌入"节点 vs "索引"节点
  // - index 阶段 + embed.start → 嵌入 running, 索引 idle
  // - index 阶段 + embed.done/failed → 嵌入 done/failed, 索引 running
  // - 其他 stage → 按 task.stage 定位
  const inIndexStage = task.stage === 'index'
  const embedRunning = inIndexStage && embedState?.action === 'start'

  const currentIndex = STAGES.findIndex((s) => s.key === task.stage)
  const effectiveIndex = currentIndex === -1 ? STAGES.length - 1 : currentIndex
  const isTerminal = task.status === 'done' || task.status === 'cancelled'
  const isFailed = task.status === 'failed'

  return STAGES.map((stage, idx) => {
    if (task.status === 'done') return 'done'
    if (idx < effectiveIndex) return 'done'
    if (idx > effectiveIndex) {
      if (isTerminal) return 'skipped'
      if (isFailed) return 'skipped'
      return 'idle'
    }
    // idx === effectiveIndex
    if (stage.key === 'embed' && inIndexStage) {
      if (embedState?.action === 'start') return 'running'
      if (embedState?.action === 'failed') return 'failed'
      if (embedState?.action === 'done' || embedState?.action === 'skipped') return 'done'
    }
    if (stage.key === 'index' && inIndexStage && embedRunning) {
      return 'idle' // 等嵌入完成
    }
    if (task.status === 'processing') return 'running'
    if (task.status === 'failed') return 'failed'
    if (task.status === 'cancelled') return 'skipped'
    return 'idle'
  })
}

function NodeIcon({ state }: { state: NodeState }) {
  if (state === 'done') return <CheckIcon size={10} />
  if (state === 'failed') return <XIcon size={10} />
  return null
}

export default function PdfPipelineFlow({
  variant,
  task,
  progressPct,
  details,
  embedState,
}: PdfPipelineFlowProps) {
  if (!task) return null

  const states = getNodeStates(task, embedState)
  const currentIndex = states.findIndex((s) => s === 'running' || s === 'failed')
  const activeIndex = currentIndex === -1 ? STAGES.findIndex((s) => s.key === task.stage) : currentIndex
  const currentStage = STAGES[activeIndex] ?? STAGES[0]
  const effectiveProgress = progressPct ?? task.progress_pct

  if (variant === 'compact') {
    return (
      <span className="pdf-pipeline-flow pdf-pipeline-flow--compact">
        {STAGES.map((stage, idx) => {
          const state = states[idx]
          return (
            <span
              key={stage.key}
              className={`pdf-pipeline-node pdf-pipeline-node--${state}`}
              title={`${stage.label}: ${state}`}
            >
              <NodeIcon state={state} />
            </span>
          )
        })}
        <span className="pdf-pipeline-current-label">{currentStage.label}</span>
      </span>
    )
  }

  return (
    <div className="pdf-pipeline-flow pdf-pipeline-flow--full">
      <div className="pdf-pipeline-steps">
        {STAGES.map((stage, idx) => {
          const state = states[idx]
          const isActive = idx === activeIndex
          return (
            <div key={stage.key} className={`pdf-pipeline-step pdf-pipeline-step--${state}`}>
              <div className="pdf-pipeline-step-icon-wrap">
                <stage.Icon size={16} />
                <span className={`pdf-pipeline-node pdf-pipeline-node--${state}`}>
                  <NodeIcon state={state} />
                </span>
              </div>
              <span className={`pdf-pipeline-step-label${isActive ? ' is-active' : ''}`}>
                {stage.label}
              </span>
              {idx < STAGES.length - 1 && <span className="pdf-pipeline-connector" />}
            </div>
          )
        })}
      </div>

      <div className="pdf-pipeline-full-meta">
        <span className="pdf-pipeline-full-stage">{currentStage.label}</span>
        {details && <span className="pdf-pipeline-full-details">{details}</span>}
        {embedState && embedState.action === 'start' && (
          <span className="pdf-pipeline-full-details" style={{ color: 'var(--info)' }}>
            嵌入中 ({embedState.model})
          </span>
        )}
      </div>

      {task.status === 'processing' && (
        <div className="pdf-pipeline-full-progress">
          <ProgressBar value={effectiveProgress} showPercent height={6} />
        </div>
      )}
    </div>
  )
}
