import { useEffect, useState, useMemo } from 'react'
import { PageContainer, PageTitle, SectionTitle, Tabs, Button, Card, EmptyState, AlertBanner, ResponsiveGrid } from './ui'
import { FlaskIcon, BarChartIcon, SparklesIcon, TargetIcon, ExternalLinkIcon } from './icons'
import CompoundCard from './sar/CompoundCard'
import RGroupMatrix from './sar/RGroupMatrix'
import CorrectionPanel from './molecule/CorrectionPanel'
import { showToast } from '../hooks/useToast'
import { useAppContext } from '../context/AppContext'
import { listMoleculesTauri, molStoreList, molStoreUpdateBatch } from '../api/tauri/molecule'
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

  // 加载矫正候选项（status=pending 的分子）
  const [correctionItems, setCorrectionItems] = useState<Array<{
    id: string
    ocrSmiles: string
    ocrConfidence: number
    name?: string
    sourceDoc?: string
    context?: string
    status?: 'pending' | 'confirmed' | 'rejected' | 'corrected'
    correctedSmiles?: string
    sourceRecord?: MoleculeRecord
  }>>([])

  useEffect(() => {
    if (activeTab !== 'correction' || !projectRoot) return
    molStoreList(projectRoot, 200, 0, undefined, 'pending')
      .then(records => {
        setCorrectionItems(
          records.map(r => ({
            id: r.mol_id,
            ocrSmiles: r.esmiles,
            ocrConfidence: 0.5, // pending 视为低置信度
            name: r.name || undefined,
            sourceDoc: r.source_doc || undefined,
            context: r.notes || undefined,
            status: 'pending' as const,
            sourceRecord: r,
          })),
        )
      })
      .catch(e => showToast(`加载待矫正分子失败: ${e instanceof Error ? e.message : String(e)}`, 'error'))
  }, [activeTab, projectRoot])
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
          { key: 'correction', label: <><SparklesIcon size={14} /> OCR 矫正</>, badge: correctionItems.length },
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
        {activeTab === 'correction' && (
          <CorrectionTab
            projectRoot={projectRoot}
            items={correctionItems}
            onItemsChange={setCorrectionItems}
            onComplete={(saved, failed) => {
              if (failed === 0 && saved > 0) {
                setCorrectionItems(prev => prev.filter(i => !i.sourceRecord || prev.find(p => p.id === i.id && p.status === 'pending')))
              }
            }}
          />
        )}
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
    <Card padding="16px" style={{
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      background: variantBg[variant],
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
    </Card>
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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <SectionTitle style={{ margin: 0 }}>
          化合物列表
        </SectionTitle>
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

function CorrectionTab({
  projectRoot,
  items,
  onItemsChange,
  onComplete,
}: {
  projectRoot: string | null
  items: Array<{
    id: string
    ocrSmiles: string
    ocrConfidence: number
    name?: string
    sourceDoc?: string
    context?: string
    status?: 'pending' | 'confirmed' | 'rejected' | 'corrected'
    correctedSmiles?: string
    sourceRecord?: MoleculeRecord
  }>
  onItemsChange: (
    items: Array<{
      id: string
      ocrSmiles: string
      ocrConfidence: number
      name?: string
      sourceDoc?: string
      context?: string
      status?: 'pending' | 'confirmed' | 'rejected' | 'corrected'
      correctedSmiles?: string
      sourceRecord?: MoleculeRecord
    }>,
  ) => void
  onComplete: (saved: number, failed: number) => void
}) {
  const [saving, setSaving] = useState(false)

  const handleItemChange = (id: string, finalSmiles: string, status: 'pending' | 'confirmed' | 'rejected' | 'corrected' | undefined) => {
    onItemsChange(
      items.map(item =>
        item.id === id
          ? { ...item, correctedSmiles: finalSmiles, status: (status ?? 'pending') as typeof item.status }
          : item,
      ),
    )
  }

  const handleComplete = async (results: Array<{ id: string; finalSmiles: string; status: 'confirmed' | 'rejected' | 'corrected' }>) => {
    if (!projectRoot) {
      showToast('未选择项目', 'warning')
      return
    }
    if (results.length === 0) {
      showToast('没有可保存的结果', 'info')
      return
    }

    setSaving(true)
    try {
      // 构造 MoleculeRecord_ 列表，保留原 metadata，只覆盖 esmiles + status + notes
      const records = results
        .map(r => {
          const item = items.find(i => i.id === r.id)
          if (!item?.sourceRecord) return null
          return {
            ...item.sourceRecord,
            esmiles: r.finalSmiles,
            status: r.status,
            notes: `${item.sourceRecord.notes || ''}\n[${new Date().toISOString()}] OCR 矫正: ${r.status}`.trim(),
          }
        })
        .filter((r): r is NonNullable<typeof r> => r !== null)

      if (records.length === 0) {
        showToast('没有可保存的记录（缺少源数据）', 'warning')
        return
      }

      const result = await molStoreUpdateBatch(projectRoot, records)
      onComplete(result.updated, result.failed.length)
      const correctedCount = results.filter(r => r.status === 'corrected').length
      if (result.failed.length > 0) {
        showToast(
          `保存完成：${result.updated} 项已保存，${result.failed.length} 项失败`,
          'warning',
        )
      } else {
        showToast(
          `保存完成：${result.updated} 项已写入数据库${correctedCount > 0 ? `，${correctedCount} 项已修正` : ''}`,
          'success',
        )
      }
    } catch (e) {
      showToast(`保存失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <AlertBanner
        variant="info"
        message={'OCR 自动识别的分子结构可能存在错误。下方展示 status=pending 的待复核分子，请逐项核对并矫正。完成时点击『完成矫正』批量保存到数据库。'}
      />
      <CorrectionPanel
        items={items}
        onComplete={handleComplete}
        onItemChange={handleItemChange}
      />
      {saving && (
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
          正在批量保存到数据库…
        </div>
      )}
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
