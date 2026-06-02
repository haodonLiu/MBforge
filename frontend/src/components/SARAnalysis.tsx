import { useEffect, useState, useMemo } from 'react'
import { PageContainer, PageTitle, Tabs, Button, EmptyState, AlertBanner, ResponsiveGrid } from './ui'
import { FlaskIcon, BarChartIcon, SparklesIcon, TargetIcon, ExternalLinkIcon } from './icons'
import CompoundCard from './sar/CompoundCard'
import RGroupMatrix from './sar/RGroupMatrix'
import CorrectionPanel from './molecule/CorrectionPanel'
import { showToast } from '../hooks/useToast'
import { useAppContext } from '../context/AppContext'
import { listMoleculesTauri } from '../api/tauri/molecule'
import type { SARSession, SARCompound, MoleculeRecord } from '../types'

// ============================================================================
// 主页面
// ============================================================================


function moleculesToSession(molecules: MoleculeRecord[]): SARSession {
  return {
    id: 'session_current',
    name: '当前项目分子',
    target: undefined,
    coreSmiles: undefined,
    createdAt: new Date().toISOString(),
    sourceDocs: [],
    compounds: molecules.map(m => ({
      id: m.mol_id,
      name: m.name || m.mol_id,
      smiles: m.esmiles,
      rGroups: {},
      activity: m.activity ?? undefined,
      activityType: m.activity_type || undefined,
      units: m.units || undefined,
      notes: m.notes || undefined,
    })),
  }
}

export default function SARAnalysis() {
  const { projectRoot } = useAppContext()
  const [sessions, setSessions] = useState<SARSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'overview' | 'correction' | 'rgroup'>('overview')
  const [selectedCompoundId, setSelectedCompoundId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  // 加载数据
  useEffect(() => {
    if (!projectRoot) {
      setLoading(false)
      return
    }
    setLoading(true)
    listMoleculesTauri(projectRoot, 200, 0)
      .then(resp => {
        const molecules = resp.success ? resp.molecules : []
        const session = moleculesToSession(molecules)
        setSessions([session])
        setActiveSessionId(session.id)
      })
      .catch(e => showToast(`加载失败: ${e.message}`, 'error'))
      .finally(() => setLoading(false))
  }, [projectRoot])

  const activeSession = useMemo(
    () => sessions.find(s => s.id === activeSessionId) ?? null,
    [sessions, activeSessionId],
  )

  if (loading) {
    return (
      <PageContainer>
        <PageTitle>SAR Analysis</PageTitle>
        <EmptyState message="正在加载 SAR 数据..." />
      </PageContainer>
    )
  }

  if (sessions.length === 0) {
    return (
      <PageContainer>
        <PageTitle>SAR Analysis</PageTitle>
        <EmptyState
          message="还没有 SAR 会话"
        />
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      {/* 顶部：标题 + Session 选择 */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24, gap: 16, flexWrap: 'wrap' }}>
        <div>
          <PageTitle>SAR Analysis</PageTitle>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
            构效关系分析 · 共 {activeSession?.compounds.length ?? 0} 个化合物
          </div>
        </div>
        {sessions.length > 1 && (
          <select
            value={activeSessionId ?? ''}
            onChange={e => setActiveSessionId(e.target.value)}
            style={{
              padding: '6px 12px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              color: 'var(--text-primary)',
              fontSize: 13,
            }}
          >
            {sessions.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        )}
      </div>

      {/* Session 概览卡片 */}
      {activeSession && (
        <div style={{ marginBottom: 20 }}>
          <SessionOverview session={activeSession} />
        </div>
      )}

      {/* Tabs */}
      <Tabs
        items={[
          { key: 'overview',   label: <><FlaskIcon size={14} /> 化合物列表</>, badge: activeSession?.compounds.length },
          { key: 'correction', label: <><SparklesIcon size={14} /> OCR 矫正</>, badge: 0 },
          { key: 'rgroup',     label: <><TargetIcon size={14} /> R-Group 分析</> },
        ]}
        activeKey={activeTab}
        onChange={k => setActiveTab(k as typeof activeTab)}
      />

      <div style={{ marginTop: 20 }}>
        {activeTab === 'overview' && activeSession && (
          <OverviewTab
            session={activeSession}
            selectedCompoundId={selectedCompoundId}
            onSelect={setSelectedCompoundId}
          />
        )}
        {activeTab === 'correction' && <CorrectionTab />}
        {activeTab === 'rgroup' && activeSession && (
          <RGroupTab
            session={activeSession}
            onSelectCompound={c => {
              setSelectedCompoundId(c.id)
              setActiveTab('overview')
              showToast(`已跳转到 ${c.name}`, 'info')
            }}
          />
        )}
      </div>
    </PageContainer>
  )
}

// ============================================================================
// Session 概览
// ============================================================================

function SessionOverview({ session }: { session: SARSession }) {
  const stats = useMemo(() => {
    const compounds = session.compounds
    const withActivity = compounds.filter(c => c.activity != null)
    const highActivity = compounds.filter(c => {
      if (c.activity == null) return false
      const nM = c.units === 'uM' ? c.activity * 1000 : c.units === 'mM' ? c.activity * 1e6 : c.activity
      return nM < 10
    }).length

    const best = compounds.reduce<SARCompound | null>((min, c) => {
      if (c.activity == null) return min
      if (!min || (c.activity < min.activity!)) return c
      return min
    }, null)

    return {
      total: compounds.length,
      tested: withActivity.length,
      high: highActivity,
      best,
    }
  }, [session])

  return (
    <ResponsiveGrid mobileColumns={1} tabletColumns={2} desktopColumns={4} gap={12}>
      <StatBox label="化合物总数" value={stats.total} icon={<FlaskIcon size={20} />} />
      <StatBox label="已测活性" value={stats.tested} icon={<BarChartIcon size={20} />} variant="info" />
      <StatBox label="高活性 (<10 nM)" value={stats.high} icon={<SparklesIcon size={20} />} variant="success" />
      <StatBox
        label="最佳化合物"
        value={stats.best?.name ?? '—'}
        subValue={stats.best ? `${stats.best.activity} ${stats.best.units}` : undefined}
        icon={<TargetIcon size={20} />}
        variant="warning"
      />
    </ResponsiveGrid>
  )
}

function StatBox({ label, value, subValue, icon, variant = 'default' }: {
  label: string
  value: string | number
  subValue?: string
  icon: React.ReactNode
  variant?: 'default' | 'success' | 'info' | 'warning' | 'danger'
}) {
  const variantBg: Record<string, string> = {
    default: 'var(--bg-surface)',
    success: 'rgba(22,163,74,0.08)',
    info: 'rgba(59,130,246,0.08)',
    warning: 'rgba(245,158,11,0.08)',
    danger: 'rgba(220,38,38,0.08)',
  }
  const variantColor: Record<string, string> = {
    default: 'var(--text-primary)',
    success: 'var(--success)',
    info: 'var(--info)',
    warning: 'var(--warning)',
    danger: 'var(--danger)',
  }
  return (
    <div style={{
      background: variantBg[variant],
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: 16,
      display: 'flex',
      alignItems: 'center',
      gap: 12,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 8,
        background: 'var(--bg-elevated)',
        color: variantColor[variant],
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
        <div style={{ fontSize: 18, fontWeight: 700, color: variantColor[variant], marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {value}
        </div>
        {subValue && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{subValue}</div>}
      </div>
    </div>
  )
}

// ============================================================================
// Tab 1: 化合物列表
// ============================================================================

function OverviewTab({
  session,
  selectedCompoundId,
  onSelect,
}: {
  session: SARSession
  selectedCompoundId: string | null
  onSelect: (id: string) => void
}) {
  // 按活性排序
  const sorted = useMemo(() => {
    return [...session.compounds].sort((a, b) => {
      const aA = a.activity ?? Infinity
      const bA = b.activity ?? Infinity
      return aA - bA
    })
  }, [session.compounds])

  return (
    <div>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 12,
      }}>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          按活性排序（IC50 从小到大）
        </div>
        <Button variant="ghost" size="sm" onClick={() => showToast('导出功能开发中', 'info')}>
          <ExternalLinkIcon size={14} /> 导出
        </Button>
      </div>
      <ResponsiveGrid mobileColumns={1} tabletColumns={2} desktopColumns={3} gap={12}>
        {sorted.map(cmp => (
          <CompoundCard
            key={cmp.id}
            compound={cmp}
            selected={selectedCompoundId === cmp.id}
            onClick={() => onSelect(cmp.id)}
            thumbnailSize={180}
          />
        ))}
      </ResponsiveGrid>
    </div>
  )
}

// ============================================================================
// Tab 2: OCR 矫正
// ============================================================================

function CorrectionTab() {
  const [items, setItems] = useState<Array<{
    id: string
    ocrSmiles: string
    ocrConfidence: number
    name?: string
    sourceDoc?: string
    context?: string
    status?: 'pending' | 'confirmed' | 'rejected' | 'corrected'
    correctedSmiles?: string
  }>>([])

  const handleComplete = (results: Array<{ id: string; finalSmiles: string; status: 'confirmed' | 'rejected' | 'corrected' }>) => {
    console.log('[SAR] Correction complete:', results)
    showToast(
      `矫正完成：${results.length} 项（${results.filter(r => r.status === 'corrected').length} 项已修正）`,
      'success',
    )
    // TODO: 调用 API 保存到后端
  }

  const handleItemChange = (id: string, finalSmiles: string, status: 'pending' | 'confirmed' | 'rejected' | 'corrected' | undefined) => {
    console.log('[SAR] Item changed:', { id, finalSmiles, status })
    setItems(prev => prev.map(item =>
      item.id === id ? { ...item, correctedSmiles: finalSmiles, status: (status ?? 'pending') as typeof item.status } : item
    ))
  }

  return (
    <div>
      <AlertBanner
        variant="info"
        message="OCR 自动识别的分子结构可能存在错误，请逐项核对并矫正。来源图像显示在左侧，OCR 识别结果显示在中间，您可以在右侧手动编辑 SMILES。"
      />
      <CorrectionPanel
        items={items}
        onComplete={handleComplete}
        onItemChange={handleItemChange}
      />
    </div>
  )
}

// ============================================================================
// Tab 3: R-Group 分析
// ============================================================================
function RGroupTab({
  session,
  onSelectCompound,
}: {
  session: SARSession
  onSelectCompound?: (compound: SARCompound) => void
}) {
  // 从 session.coreSmiles 推断 lower_is_better：
  // IC50/EC50/Ki 通常 lower is better，%inhibition 等设 false
  // 默认 lower_is_better=true（药物化学 IC50 场景最常见）
  return (
    <div>
      <AlertBanner
        variant="info"
        message="R-Group 分析自动从化合物结构中提取共同骨架（MCS 算法），无需手动标记 R 取代基位置。IC50 数值越低表示活性越高。"
      />
      <RGroupMatrix
        compounds={session.compounds}
        coreSmiles={session.coreSmiles}
        lowerIsBetter
        onCompoundClick={onSelectCompound}
      />
    </div>
  )
}
