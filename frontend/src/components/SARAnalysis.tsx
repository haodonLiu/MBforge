import { useEffect, useState, useMemo } from 'react'
import { PageContainer, PageTitle, Tabs, EmptyState } from './ui'
import { FlaskIcon, BarChartIcon, SparklesIcon, TargetIcon } from './icons'
import { showToast } from '../hooks/useToast'
import { useAppContext } from '../context/AppContext'
import { listMoleculesTauri, molStoreList } from '../api/tauri/molecule'
import type { MoleculeRecord } from '../types'
import type { SARSession } from '../types'
import { moleculesToSession } from './sar/utils'
import SessionOverview from './sar/SessionOverview'
import OverviewTab from './sar/OverviewTab'
import CorrectionTab from './sar/CorrectionTab'
import RGroupTab from './sar/RGroupTab'
import CliffsTab from './sar/CliffsTab'

export default function SARAnalysis() {
  const { projectRoot } = useAppContext()
  const [sessions, setSessions] = useState<SARSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'overview' | 'correction' | 'rgroup' | 'cliffs'>('overview')
  const [selectedCompoundId, setSelectedCompoundId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

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
            ocrConfidence: 0.5,
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
        <EmptyState message="还没有 SAR 会话" />
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <div className="sar-header">
        <div>
          <PageTitle>SAR Analysis</PageTitle>
          <div className="sar-header-subtitle">
            构效关系分析 · 共 {activeSession?.compounds.length ?? 0} 个化合物
          </div>
        </div>
        {sessions.length > 1 && (
          <select
            value={activeSessionId ?? ''}
            onChange={e => setActiveSessionId(e.target.value)}
            className="sar-session-select"
          >
            {sessions.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        )}
      </div>

      {activeSession && (
        <div className="sar-overview-wrap">
          <SessionOverview session={activeSession} />
        </div>
      )}

      <Tabs
        items={[
          { key: 'overview',   label: <><FlaskIcon size={14} /> 化合物列表</>, badge: activeSession?.compounds.length },
          { key: 'correction', label: <><SparklesIcon size={14} /> OCR 矫正</>, badge: correctionItems.length },
          { key: 'rgroup',     label: <><TargetIcon size={14} /> R-Group 分析</> },
          { key: 'cliffs',     label: <><BarChartIcon size={14} /> 活性悬崖</> },
        ]}
        activeKey={activeTab}
        onChange={k => setActiveTab(k as typeof activeTab)}
      />

      <div className="sar-tab-content">
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
        {activeTab === 'cliffs' && activeSession && (
          <CliffsTab session={activeSession} />
        )}
      </div>
    </PageContainer>
  )
}
