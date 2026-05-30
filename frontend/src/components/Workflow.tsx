import { motion } from 'framer-motion'
import { StaggerContainer, StaggerItem } from './animations/StaggerContainer'
import { TargetIcon, BarChartIcon, ClockIcon, CheckIcon } from './icons'
import PageContainer from '../components/ui/PageContainer'
import PageTitle from '../components/ui/PageTitle'
import CardGrid from '../components/ui/CardGrid'
import HoverCard from '../components/ui/HoverCard'
import IconContainer from '../components/ui/IconContainer'
import BodyText from '../components/ui/BodyText'
import Caption from '../components/ui/Caption'

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
    <PageContainer>
      <PageTitle>工作流中心</PageTitle>
      <BodyText style={{ marginBottom: '24px' }}>
        选择一个工作流开始执行分子相关任务
      </BodyText>

      <StaggerContainer>
        <CardGrid minWidth={320} gap={16}>
          {WORKFLOWS.map(wf => (
            <StaggerItem key={wf.id}>
              <HoverCard
                style={{
                  position: 'relative',
                  padding: '24px',
                  borderRadius: '14px',
                  cursor: 'pointer',
                  ...(wf.status === 'pending' ? { opacity: 0.7, filter: 'grayscale(0.5)' } : {}),
                }}
              >
                {wf.status === 'ready' && (
                  <motion.div
                    animate={{ boxShadow: ['0 0 0 0px rgba(26,26,26,0)', '0 0 0 2px rgba(26,26,26,0.08)', '0 0 0 0px rgba(26,26,26,0)'] }}
                    transition={{ repeat: Infinity, duration: 2 }}
                    style={{
                      position: 'absolute',
                      inset: 0,
                      borderRadius: '14px',
                      pointerEvents: 'none',
                    }}
                  />
                )}
                <motion.div whileHover={{ rotate: 5 }}>
                  <IconContainer size={48} style={{ marginBottom: '16px' }}>
                    {wf.icon}
                  </IconContainer>
                </motion.div>
                <h3 style={{
                  fontSize: '16px',
                  fontWeight: 600,
                  marginBottom: '8px',
                }}>{wf.name}</h3>
                <BodyText size="sm" style={{ marginBottom: '16px' }}>
                  {wf.description}
                </BodyText>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}>
                  <span style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    background: wf.status === 'ready' ? '#16a34a' : '#f59e0b',
                  }} />
                  <Caption>{wf.engine}</Caption>
                </div>
              </HoverCard>
            </StaggerItem>
          ))}
        </CardGrid>
      </StaggerContainer>
    </PageContainer>
  )
}
