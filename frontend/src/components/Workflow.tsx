import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { showToast } from '../hooks/useToast'
import { StaggerContainer, StaggerItem } from './animations/StaggerContainer'
import { TargetIcon, BarChartIcon, CpuIcon, DnaIcon, FlaskIcon, RefreshCwIcon } from './icons'
import { 
  PageContainer, 
  PageTitle, 
  CardGrid, 
  HoverCard, 
  IconContainer, 
  BodyText, 
  Caption,
  StatusBadge,
  EnvCard,
  LibStatusRow,
  CollapsibleSection,
} from './ui'
import type { StatusType } from './ui/StatusBadge'

interface CapabilityStatus {
  name: string
  available: boolean
  version: string | null
  description: string
  category: string
}

interface EnvironmentCheckResult {
  python_version: string
  gpu_available: boolean
  gpu_name: string | null
  gpu_memory_mb: number | null
  capabilities: CapabilityStatus[]
}

// 库信息
const LIBRARY_INFO: Record<string, { name: string; hint?: string }> = {
  rdkit:    { name: 'RDKit', hint: '分子信息学' },
  numpy:    { name: 'NumPy', hint: '数值计算' },
  scipy:    { name: 'SciPy', hint: '科学计算' },
  pandas:   { name: 'Pandas', hint: '数据分析' },
  openmm:   { name: 'OpenMM', hint: '分子动力学' },
  vina:     { name: 'AutoDock Vina', hint: '分子对接' },
  deepchem: { name: 'DeepChem', hint: 'ADMET 预测' },
  torch:    { name: 'PyTorch', hint: '深度学习' },
}

// 工作流定义
const WORKFLOWS = [
  {
    id: 'sar',
    name: 'SAR 分析',
    description: '分析化合物结构-活性关系，识别关键药效团和构效关系',
    engine: 'MBForge 内置',
    requires: ['rdkit'],
    icon: <BarChartIcon size={24} />,
  },
  {
    id: 'moldraw',
    name: '分子绘制',
    description: '可视化分子结构，编辑 SMILES 和查看属性',
    engine: 'RDKit',
    requires: ['rdkit'],
    icon: <CpuIcon size={24} />,
  },
  {
    id: 'docking',
    name: '分子对接',
    description: '将小分子配体与蛋白质受体进行对接，预测结合模式和亲和力',
    engine: 'AutoDock Vina',
    requires: ['vina'],
    icon: <TargetIcon size={24} />,
  },
  {
    id: 'md',
    name: '分子动力学',
    description: '模拟分子在原子层面的动态行为，研究构象变化和相互作用',
    engine: 'OpenMM',
    requires: ['openmm'],
    icon: <DnaIcon size={24} />,
  },
  {
    id: 'admet',
    name: 'ADMET 预测',
    description: '预测化合物的吸收、分布、代谢、排泄和毒性特性',
    engine: 'DeepChem',
    requires: ['deepchem'],
    icon: <FlaskIcon size={24} />,
  },
]

function getWorkflowStatus(workflow: typeof WORKFLOWS[0], env: EnvironmentCheckResult | null): StatusType {
  if (!env) return 'pending'
  
  const hasCore = env.capabilities.some(c => c.name === 'rdkit' && c.available)
  
  if (workflow.id === 'sar' || workflow.id === 'moldraw') {
    return hasCore ? 'ready' : 'error'
  }
  
  const hasRequired = env.capabilities.some(c => workflow.requires.includes(c.name) && c.available)
  if (hasRequired) return 'ready'
  if (hasCore) return 'warning'
  return 'pending'
}

function getStatusText(status: StatusType): string {
  switch (status) {
    case 'ready': return '就绪'
    case 'warning': return '需安装依赖'
    case 'error': return '缺少核心库'
    default: return '尚未配置'
  }
}

// 环境状态面板
function EnvironmentPanel({ env, loading }: { env: EnvironmentCheckResult | null; loading: boolean }) {
  if (loading) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '32px',
          background: '#fafafa',
          borderRadius: '12px',
          border: '1px solid #e5e5e5',
          marginBottom: '24px',
        }}
      >
        <RefreshCwIcon size={18} style={{ color: '#666', marginRight: '10px' }} />
        <span style={{ color: '#666', fontSize: '14px' }}>正在检测运行环境...</span>
      </motion.div>
    )
  }

  if (!env) return null

  const coreLibs = env.capabilities.filter(c => c.category === 'core')
  const mdLibs = env.capabilities.filter(c => c.category === 'md')
  const dockingLibs = env.capabilities.filter(c => c.category === 'docking')
  const admetLibs = env.capabilities.filter(c => c.category === 'admet')
  
  const hasMissing = env.capabilities.some(c => !c.available)

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        marginBottom: '24px',
        borderRadius: '12px',
        border: '1px solid #e5e5e5',
        overflow: 'hidden',
        background: '#fff',
      }}
    >
      {/* 标题栏 */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 16px',
        background: '#fafafa',
        borderBottom: '1px solid #e5e5e5',
      }}>
        <span style={{ fontWeight: 600, fontSize: '14px' }}>Environment Status</span>
        <div style={{ display: 'flex', gap: '12px' }}>
          <EnvCard label="Python" value={env.python_version} />
          <EnvCard 
            label="GPU" 
            value={env.gpu_name || 'None'} 
            subValue={env.gpu_memory_mb ? `${Math.round(env.gpu_memory_mb / 1024)}GB` : undefined}
            variant={env.gpu_available ? 'success' : 'default'}
          />
        </div>
      </div>

      {/* 库状态列表 */}
      <div style={{ padding: '16px' }}>
        <CollapsibleSection title="Core Libraries" badge={coreLibs.length}>
          {coreLibs.map(cap => {
            const info = LIBRARY_INFO[cap.name] || { name: cap.name }
            return (
              <LibStatusRow 
                key={cap.name} 
                name={info.name} 
                version={cap.version} 
                available={cap.available}
                hint={info.hint}
              />
            )
          })}
        </CollapsibleSection>

        <CollapsibleSection title="Molecular Dynamics" badge={mdLibs.length}>
          {mdLibs.length > 0 ? mdLibs.map(cap => {
            const info = LIBRARY_INFO[cap.name] || { name: cap.name }
            return (
              <LibStatusRow 
                key={cap.name} 
                name={info.name} 
                version={cap.version} 
                available={cap.available}
                hint={info.hint}
              />
            )
          }) : (
            <div style={{ padding: '12px 0', color: '#999', fontSize: '13px' }}>
              No molecular dynamics tools installed
            </div>
          )}
        </CollapsibleSection>

        <CollapsibleSection title="Docking" badge={dockingLibs.length}>
          {dockingLibs.length > 0 ? dockingLibs.map(cap => {
            const info = LIBRARY_INFO[cap.name] || { name: cap.name }
            return (
              <LibStatusRow 
                key={cap.name} 
                name={info.name} 
                version={cap.version} 
                available={cap.available}
                hint={info.hint}
              />
            )
          }) : (
            <div style={{ padding: '12px 0', color: '#999', fontSize: '13px' }}>
              No docking tools installed
            </div>
          )}
        </CollapsibleSection>

        <CollapsibleSection title="ADMET" badge={admetLibs.length}>
          {admetLibs.length > 0 ? admetLibs.map(cap => {
            const info = LIBRARY_INFO[cap.name] || { name: cap.name }
            return (
              <LibStatusRow 
                key={cap.name} 
                name={info.name} 
                version={cap.version} 
                available={cap.available}
                hint={info.hint}
              />
            )
          }) : (
            <div style={{ padding: '12px 0', color: '#999', fontSize: '13px' }}>
              No ADMET tools installed
            </div>
          )}
        </CollapsibleSection>

        {hasMissing && (
          <div style={{
            marginTop: '16px',
            padding: '12px 16px',
            background: '#fef3c7',
            border: '1px solid #f59e0b',
            borderRadius: '6px',
            color: '#92400e',
            fontSize: '13px',
          }}>
            部分工具未安装。运行 <code style={{ background: '#fff', padding: '2px 6px', borderRadius: '4px' }}>uv add openmm deepchem</code> 安装。
          </div>
        )}
      </div>
    </motion.div>
  )
}

export default function Workflow() {
  const [env, setEnv] = useState<EnvironmentCheckResult | null>(null)
  const [loading, setLoading] = useState(true)

  const handleWorkflow = useCallback((wf: typeof WORKFLOWS[0]) => {
    const status = getWorkflowStatus(wf, env)
    if (status !== 'ready') {
      showToast(`${wf.name} 需要安装依赖: ${wf.requires.join(', ')}`, 'info')
      return
    }
    // 根据工作流类型跳转或打开面板
    switch (wf.id) {
      case 'sar':
        showToast('SAR 分析功能开发中...', 'info')
        break
      case 'moldraw':
        showToast('分子绘制功能开发中...', 'info')
        break
      case 'docking':
        showToast('分子对接功能开发中...', 'info')
        break
      case 'md':
        showToast('分子动力学功能开发中...', 'info')
        break
      case 'admet':
        showToast('ADMET 预测功能开发中...', 'info')
        break
      default:
        showToast(`${wf.name}: 功能开发中`, 'info')
    }
  }, [env])

  useEffect(() => {
    async function checkEnvironment() {
      try {
        const response = await fetch('/api/v1/environment/check')
        if (response.ok) {
          const data = await response.json()
          setEnv(data)
        }
      } catch (e) {
        console.error('Environment check failed:', e)
      } finally {
        setLoading(false)
      }
    }
    checkEnvironment()
  }, [])

  return (
    <PageContainer>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
        <PageTitle>Workflow Center</PageTitle>
      </div>

      <EnvironmentPanel env={env} loading={loading} />

      <BodyText style={{ marginBottom: '16px' }}>
        Select a workflow to start molecular tasks
      </BodyText>

      <StaggerContainer>
        <CardGrid minWidth={280} gap={16}>
          {WORKFLOWS.map(wf => {
            const status = getWorkflowStatus(wf, env)
            const isReady = status === 'ready'
            
            return (
              <StaggerItem key={wf.id}>
                <HoverCard
                  onClick={() => handleWorkflow(wf)}
                  style={{
                    position: 'relative',
                    padding: '24px',
                    borderRadius: '14px',
                    cursor: isReady ? 'pointer' : 'not-allowed',
                    opacity: status === 'pending' ? 0.5 : 1,
                    transition: 'all 0.2s ease',
                  }}
                >
                  {isReady && (
                    <motion.div
                      animate={{ 
                        boxShadow: [
                          '0 0 0 0px rgba(22, 163, 74, 0)',
                          '0 0 0 3px rgba(22, 163, 74, 0.15)',
                          '0 0 0 0px rgba(22, 163, 74, 0)'
                        ]
                      }}
                      transition={{ repeat: Infinity, duration: 3 }}
                      style={{
                        position: 'absolute',
                        inset: 0,
                        borderRadius: '14px',
                        pointerEvents: 'none',
                      }}
                    />
                  )}
                  
                  <div style={{ position: 'absolute', top: '12px', right: '12px' }}>
                    <StatusBadge type={status}>{getStatusText(status)}</StatusBadge>
                  </div>
                  
                  <motion.div whileHover={isReady ? { scale: 1.02 } : {}}>
                    <IconContainer 
                      size={48} 
                      style={{ 
                        marginBottom: '16px',
                        background: isReady ? '#f0fdf4' : '#fafafa',
                      }}
                    >
                      {wf.icon}
                    </IconContainer>
                  </motion.div>
                  
                  <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                    {wf.name}
                  </h3>
                  
                  <BodyText size="sm" style={{ marginBottom: '12px', color: '#666' }}>
                    {wf.description}
                  </BodyText>
                  
                  <Caption>{wf.engine}</Caption>
                </HoverCard>
              </StaggerItem>
            )
          })}
        </CardGrid>
      </StaggerContainer>
    </PageContainer>
  )
}
