import type { FC } from 'react'
import { TargetIcon, FileTextIcon, EyeIcon, CheckIcon, XIcon, FlaskIcon, NetworkIcon } from '../../icons'
import type { IngestTask } from '@/api/http/ingest_queue'
import ProgressBar from '@/components/ui/ProgressBar'
import '../../../styles/pdf-pipeline-flow.css'

type PipelineVariant = 'compact' | 'full'

interface PdfPipelineFlowProps {
  variant: PipelineVariant
  task: IngestTask | null
  progressPct?: number
  details?: string
}

const STAGES: { key: string; label: string; Icon: FC<{ size?: number }> }[] = [
  { key: 'inspector', label: '文档检测', Icon: TargetIcon },
  { key: 'text_extract', label: '文本提取', Icon: FileTextIcon },
  { key: 'ocr', label: 'OCR', Icon: EyeIcon },
  { key: 'moldet', label: '分子扫描', Icon: FlaskIcon },
  { key: 'index', label: '索引构建', Icon: NetworkIcon },
]

type NodeState = 'idle' | 'running' | 'done' | 'failed' | 'skipped'

function getNodeStates(task: IngestTask): NodeState[] {
  const currentIndex = STAGES.findIndex((s) => s.key === task.stage)
  const effectiveIndex = currentIndex === -1 ? STAGES.length - 1 : currentIndex
  const isTerminal = task.status === 'done' || task.status === 'cancelled'
  const isFailed = task.status === 'failed'

  return STAGES.map((_stage, idx) => {
    if (task.status === 'done') return 'done'
    if (idx < effectiveIndex) return 'done'
    if (idx > effectiveIndex) {
      if (isTerminal) return 'skipped'
      if (isFailed) return 'skipped'
      return 'idle'
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
}: PdfPipelineFlowProps) {
  if (!task) return null

  const states = getNodeStates(task)
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
      </div>

      {task.status === 'processing' && (
        <div className="pdf-pipeline-full-progress">
          <ProgressBar value={effectiveProgress} showPercent height={6} />
        </div>
      )}
    </div>
  )
}
