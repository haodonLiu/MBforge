import { TargetIcon, BarChartIcon, ClockIcon, CheckIcon } from './icons'

interface WorkflowItem {
  id: string
  name: string
  description: string
  status: 'ready' | 'pending'
  engine: string
  icon: React.ReactNode
}

const WORKFLOWS: WorkflowItem[] = [
  {
    id: 'docking',
    name: '分子对接',
    description: '将小分子配体与蛋白质受体进行对接，预测结合模式和亲和力',
    status: 'ready',
    engine: 'UniDock 引擎就绪',
    icon: <TargetIcon size={24} />,
  },
  {
    id: 'sar',
    name: 'SAR 分析',
    description: '分析化合物结构-活性关系，识别关键药效团和构效关系',
    status: 'ready',
    engine: 'openSAR 就绪',
    icon: <BarChartIcon size={24} />,
  },
  {
    id: 'md',
    name: '分子动力学',
    description: '模拟分子在原子层面的动态行为，研究构象变化和相互作用',
    status: 'pending',
    engine: '尚未配置',
    icon: <ClockIcon size={24} />,
  },
  {
    id: 'admet',
    name: 'ADMET 预测',
    description: '预测化合物的吸收、分布、代谢、排泄和毒性特性',
    status: 'pending',
    engine: '尚未配置',
    icon: <CheckIcon size={24} />,
  },
]

export default function Workflow() {
  return (
    <div style={{
      flex: 1,
      padding: '32px',
      overflow: 'auto',
    }}>
      <h1 style={{
        fontSize: 'var(--font-size-title)',
        fontWeight: 600,
        marginBottom: '8px',
      }}>工作流中心</h1>
      <p style={{
        color: 'var(--text-secondary)',
        marginBottom: '24px',
      }}>选择一个工作流开始执行分子相关任务</p>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
        gap: '16px',
      }}>
        {WORKFLOWS.map(wf => (
          <div
            key={wf.id}
            style={{
              padding: '24px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: '14px',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'var(--accent)'
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.06)'
              e.currentTarget.style.transform = 'translateY(-2px)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.boxShadow = 'none'
              e.currentTarget.style.transform = 'translateY(0)'
            }}
          >
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'var(--accent-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--accent)',
              marginBottom: '16px',
            }}>
              {wf.icon}
            </div>
            <h3 style={{
              fontSize: '16px',
              fontWeight: 600,
              marginBottom: '8px',
            }}>{wf.name}</h3>
            <p style={{
              fontSize: '13px',
              color: 'var(--text-secondary)',
              lineHeight: 1.5,
              marginBottom: '16px',
            }}>{wf.description}</p>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: '13px',
            }}>
              <span style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: wf.status === 'ready' ? '#16a34a' : '#f59e0b',
              }} />
              <span style={{ color: 'var(--text-muted)' }}>{wf.engine}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
