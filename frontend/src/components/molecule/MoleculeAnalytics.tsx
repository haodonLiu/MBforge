import { useState, useEffect, useCallback } from 'react'
import { useAppContext } from '../../context/AppContext'
import { useTranslation } from 'react-i18next'
import { showToast } from '../../hooks/useToast'
import {
  molStoreInit,
  molSearchSubstructure,
  molFindAnalogsWithActivity,
  molListClusters,
  molGetClusterMembers,
  molAssignCluster,
  molRemoveFromCluster,
  molGetStats,
  molFindByMolecule,
  molAddRelation,
  molDeleteRelation,
  molDedupBatch,
  listMoleculesTauri,
} from '../../api/tauri/molecule'
import type {
  ClusterInfo,
  MoleculeRelation,
  RelationStats,
  DedupResult,
  AnalogWithActivity,
  SubstructureMatch,
} from '../../api/tauri/molecule'
import type { MoleculeRecord } from '../../types'
import {
  PageContainer,
  PageTitle,
  Button,
  Input,
  EmptyState,
  Card,
  SectionTitle,
  AlertBanner,
  Tabs,
  TabPanel,
  Slider,
  DataTable,
  StatCard,
  ResponsiveStatGrid,
} from '../ui'
import { SearchIcon, FlaskIcon, NetworkIcon, ClusterIcon, FilterIcon } from '../icons'

type AnalyticsTab = 'substructure' | 'analogs' | 'clusters' | 'relations' | 'dedup'

export default function MoleculeAnalytics() {
  const { projectRoot } = useAppContext()
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('substructure')
  const [molecules, setMolecules] = useState<MoleculeRecord[]>([])
  const [loadingMols, setLoadingMols] = useState(false)

  const initAndLoad = useCallback(async () => {
    if (!projectRoot) return
    setLoadingMols(true)
    try {
      await molStoreInit(projectRoot)
      const resp = await listMoleculesTauri(projectRoot, 500, 0)
      if (resp.success) {
        setMolecules(resp.molecules)
      }
    } catch (e) {
      showToast(t('mol.loadFailed'), 'error')
    } finally {
      setLoadingMols(false)
    }
  }, [projectRoot, t])

  useEffect(() => {
    initAndLoad()
  }, [initAndLoad])

  if (!projectRoot) {
    return (
      <PageContainer>
        <EmptyState message={t('mol.noProject')} />
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <PageTitle>{t('mol.analyticsTitle') ?? '分子高级分析'}</PageTitle>
        <Button variant="secondary" size="sm" onClick={initAndLoad} loading={loadingMols}>
          刷新
        </Button>
      </div>

      <Tabs
        items={[
          { key: 'substructure', label: <><SearchIcon size={14} /> 子结构搜索</> },
          { key: 'analogs', label: <><FlaskIcon size={14} /> 活性类似物</> },
          { key: 'clusters', label: <><ClusterIcon size={14} /> 聚类分析</> },
          { key: 'relations', label: <><NetworkIcon size={14} /> 关系网络</> },
          { key: 'dedup', label: <><FilterIcon size={14} /> 批量去重</> },
        ]}
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as AnalyticsTab)}
      />

      <div style={{ marginTop: 16 }}>
        <TabPanel activeKey={activeTab} tabKey="substructure">
          <SubstructureSearchPanel />
        </TabPanel>
        <TabPanel activeKey={activeTab} tabKey="analogs">
          <AnalogSearchPanel molecules={molecules} />
        </TabPanel>
        <TabPanel activeKey={activeTab} tabKey="clusters">
          <ClusterPanel molecules={molecules} />
        </TabPanel>
        <TabPanel activeKey={activeTab} tabKey="relations">
          <RelationPanel molecules={molecules} />
        </TabPanel>
        <TabPanel activeKey={activeTab} tabKey="dedup">
          <DedupPanel molecules={molecules} onComplete={initAndLoad} />
        </TabPanel>
      </div>
    </PageContainer>
  )
}

// ============================================================================
// 子结构搜索
// ============================================================================

function SubstructureSearchPanel() {
  const [query, setQuery] = useState('')
  const [threshold, setThreshold] = useState(0.3)
  const [results, setResults] = useState<SubstructureMatch[]>([])
  const [loading, setLoading] = useState(false)

  const handleSearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    try {
      const matches = await molSearchSubstructure(query.trim(), threshold)
      setResults(matches)
      if (matches.length === 0) showToast('未找到匹配分子', 'info')
    } catch (e) {
      showToast(`搜索失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 240 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              查询子结构 SMILES
            </div>
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="例如: c1ccccc1"
            />
          </div>
          <div style={{ width: 200 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              Tanimoto 预过滤阈值: {threshold.toFixed(2)}
            </div>
            <Slider min={0.1} max={0.9} step={0.05} value={threshold} onChange={(v) => setThreshold(v)} />
          </div>
          <Button variant="primary" size="sm" onClick={handleSearch} loading={loading}>
            搜索
          </Button>
        </div>
      </Card>

      {results.length > 0 && (
        <DataTable
          columns={[
            { key: 'mol_id', title: '分子 ID', width: 200 },
            { key: 'esmiles', title: 'E-SMILES', render: (row: SubstructureMatch) => (
              <code style={{ fontSize: 11, wordBreak: 'break-all' }}>{row.esmiles}</code>
            )},
          ]}
          data={results}
        />
      )}
    </div>
  )
}

// ============================================================================
// 活性类似物
// ============================================================================

function AnalogSearchPanel({ molecules }: { molecules: MoleculeRecord[] }) {
  const [selectedId, setSelectedId] = useState('')
  const [minSim, setMinSim] = useState(0.7)
  const [results, setResults] = useState<AnalogWithActivity[]>([])
  const [loading, setLoading] = useState(false)

  const handleSearch = async () => {
    if (!selectedId.trim()) return
    setLoading(true)
    try {
      const analogs = await molFindAnalogsWithActivity(selectedId.trim(), minSim)
      setResults(analogs)
      if (analogs.length === 0) showToast('未找到活性类似物', 'info')
    } catch (e) {
      showToast(`搜索失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              参考分子 ID
            </div>
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'var(--bg-base)',
                color: 'var(--text-primary)',
                fontSize: 13,
              }}
            >
              <option value="">选择分子…</option>
              {molecules.map((m) => (
                <option key={m.mol_id} value={m.mol_id}>
                  {m.name || m.mol_id} ({m.esmiles.slice(0, 30)}…)
                </option>
              ))}
            </select>
          </div>
          <div style={{ width: 200 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              最小相似度: {minSim.toFixed(2)}
            </div>
            <Slider min={0.3} max={0.99} step={0.05} value={minSim} onChange={(v) => setMinSim(v)} />
          </div>
          <Button variant="primary" size="sm" onClick={handleSearch} loading={loading}>
            查找类似物
          </Button>
        </div>
      </Card>

      {results.length > 0 && (
        <DataTable
          columns={[
            { key: 'mol_id', title: '分子 ID', width: 160 },
            { key: 'name', title: '名称', width: 140 },
            { key: 'similarity_score', title: '相似度', render: (row: AnalogWithActivity) => `${(row.similarity_score * 100).toFixed(1)}%` },
            { key: 'activity', title: '活性', render: (row: AnalogWithActivity) =>
              row.activity != null ? `${row.activity.toFixed(2)} ${row.units}` : '—'
            },
            { key: 'esmiles', title: 'E-SMILES', render: (row: AnalogWithActivity) => (
              <code style={{ fontSize: 11, wordBreak: 'break-all' }}>{row.esmiles}</code>
            )},
          ]}
          data={results}
        />
      )}
    </div>
  )
}

// ============================================================================
// 聚类分析
// ============================================================================

function ClusterPanel({ molecules }: { molecules: MoleculeRecord[] }) {
  const [clusters, setClusters] = useState<ClusterInfo[]>([])
  const [selectedCluster, setSelectedCluster] = useState<ClusterInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [assignMolId, setAssignMolId] = useState('')
  const [assignClusterId, setAssignClusterId] = useState('')

  const loadClusters = async () => {
    setLoading(true)
    try {
      const list = await molListClusters()
      setClusters(list)
    } catch (e) {
      showToast(`加载聚类失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadClusters()
  }, [])

  const handleAssign = async () => {
    if (!assignMolId || !assignClusterId) return
    try {
      await molAssignCluster(assignMolId, assignClusterId)
      showToast('聚类分配成功', 'success')
      loadClusters()
      setAssignMolId('')
      setAssignClusterId('')
    } catch (e) {
      showToast(`分配失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  const handleRemove = async (molId: string, clusterId: string) => {
    try {
      await molRemoveFromCluster(molId, clusterId)
      showToast('移除成功', 'success')
      loadClusters()
      if (selectedCluster?.cluster_id === clusterId) {
        const updated = await molGetClusterMembers(clusterId)
        setSelectedCluster(updated)
      }
    } catch (e) {
      showToast(`移除失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              分子 ID
            </div>
            <select
              value={assignMolId}
              onChange={(e) => setAssignMolId(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'var(--bg-base)',
                color: 'var(--text-primary)',
                fontSize: 13,
              }}
            >
              <option value="">选择分子…</option>
              {molecules.map((m) => (
                <option key={m.mol_id} value={m.mol_id}>
                  {m.name || m.mol_id}
                </option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              聚类 ID
            </div>
            <Input value={assignClusterId} onChange={(e) => setAssignClusterId(e.target.value)} placeholder="输入聚类标识" />
          </div>
          <Button variant="primary" size="sm" onClick={handleAssign}>
            分配
          </Button>
          <Button variant="secondary" size="sm" onClick={loadClusters} loading={loading}>
            刷新列表
          </Button>
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
        {clusters.map((c) => (
          <Card
            key={c.cluster_id}
            hoverable
            onClick={async () => {
              try {
                const info = await molGetClusterMembers(c.cluster_id)
                setSelectedCluster(info)
              } catch (e) {
                showToast('获取聚类成员失败', 'error')
              }
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{c.cluster_id}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>成员: {c.member_count}</div>
          </Card>
        ))}
      </div>

      {selectedCluster && (
        <Card>
          <SectionTitle>聚类: {selectedCluster.cluster_id} ({selectedCluster.members.length} 成员)</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
            {selectedCluster.members.map((molId) => (
              <div
                key={molId}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '6px 8px',
                  background: 'var(--bg-base)',
                  borderRadius: 4,
                }}
              >
                <code style={{ fontSize: 12 }}>{molId}</code>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => handleRemove(molId, selectedCluster.cluster_id)}
                >
                  移除
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

// ============================================================================
// 关系网络
// ============================================================================

function RelationPanel({ molecules }: { molecules: MoleculeRecord[] }) {
  const [stats, setStats] = useState<RelationStats | null>(null)
  const [searchMolId, setSearchMolId] = useState('')
  const [relations, setRelations] = useState<MoleculeRelation[]>([])
  const [loading, setLoading] = useState(false)

  // 添加关系表单
  const [newRelA, setNewRelA] = useState('')
  const [newRelB, setNewRelB] = useState('')
  const [newRelType, setNewRelType] = useState<'similar' | 'same_as' | 'scaffold' | 'cluster'>('similar')
  const [newRelScore, setNewRelScore] = useState('')

  const loadStats = async () => {
    try {
      const s = await molGetStats()
      setStats(s)
    } catch (e) {
      showToast('加载关系统计失败', 'error')
    }
  }

  useEffect(() => {
    loadStats()
  }, [])

  const handleSearchRelations = async () => {
    if (!searchMolId.trim()) return
    setLoading(true)
    try {
      const list = await molFindByMolecule(searchMolId.trim())
      setRelations(list)
    } catch (e) {
      showToast(`查询失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleAddRelation = async () => {
    if (!newRelA || !newRelB) return
    try {
      await molAddRelation(newRelA, newRelB, newRelType, newRelScore ? parseFloat(newRelScore) : undefined)
      showToast('关系添加成功', 'success')
      loadStats()
      setNewRelA('')
      setNewRelB('')
      setNewRelScore('')
    } catch (e) {
      showToast(`添加失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  const handleDeleteRelation = async (id: number) => {
    try {
      await molDeleteRelation(id)
      showToast('关系已删除', 'success')
      setRelations((prev) => prev.filter((r) => r.id !== id))
      loadStats()
    } catch (e) {
      showToast(`删除失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {stats && (
        <ResponsiveStatGrid>
          <StatCard label="总关系数" value={stats.total} />
          <StatCard label="相似" value={stats.similar} />
          <StatCard label="等价" value={stats.same_as} />
          <StatCard label="骨架" value={stats.scaffold} />
          <StatCard label="聚类" value={stats.cluster} />
        </ResponsiveStatGrid>
      )}

      <Card>
        <SectionTitle>添加关系</SectionTitle>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap', marginTop: 8 }}>
          <div style={{ flex: 1, minWidth: 160 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>分子 A</div>
            <select
              value={newRelA}
              onChange={(e) => setNewRelA(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'var(--bg-base)',
                color: 'var(--text-primary)',
                fontSize: 13,
              }}
            >
              <option value="">选择…</option>
              {molecules.map((m) => (
                <option key={m.mol_id} value={m.mol_id}>{m.name || m.mol_id}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1, minWidth: 160 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>分子 B</div>
            <select
              value={newRelB}
              onChange={(e) => setNewRelB(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'var(--bg-base)',
                color: 'var(--text-primary)',
                fontSize: 13,
              }}
            >
              <option value="">选择…</option>
              {molecules.map((m) => (
                <option key={m.mol_id} value={m.mol_id}>{m.name || m.mol_id}</option>
              ))}
            </select>
          </div>
          <div style={{ width: 140 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>类型</div>
            <select
              value={newRelType}
              onChange={(e) => setNewRelType(e.target.value as typeof newRelType)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'var(--bg-base)',
                color: 'var(--text-primary)',
                fontSize: 13,
              }}
            >
              <option value="similar">相似</option>
              <option value="same_as">等价</option>
              <option value="scaffold">骨架</option>
              <option value="cluster">聚类</option>
            </select>
          </div>
          <div style={{ width: 100 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>得分</div>
            <Input value={newRelScore} onChange={(e) => setNewRelScore(e.target.value)} placeholder="0.0-1.0" />
          </div>
          <Button variant="primary" size="sm" onClick={handleAddRelation}>
            添加
          </Button>
        </div>
      </Card>

      <Card>
        <SectionTitle>按分子查询关系</SectionTitle>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginTop: 8 }}>
          <div style={{ flex: 1 }}>
            <select
              value={searchMolId}
              onChange={(e) => setSearchMolId(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'var(--bg-base)',
                color: 'var(--text-primary)',
                fontSize: 13,
              }}
            >
              <option value="">选择分子…</option>
              {molecules.map((m) => (
                <option key={m.mol_id} value={m.mol_id}>{m.name || m.mol_id}</option>
              ))}
            </select>
          </div>
          <Button variant="secondary" size="sm" onClick={handleSearchRelations} loading={loading}>
            查询
          </Button>
        </div>

        {relations.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <DataTable
              columns={[
                { key: 'mol_a_id', title: '分子 A', width: 140 },
                { key: 'mol_b_id', title: '分子 B', width: 140 },
                { key: 'relation_type', title: '类型', width: 100 },
                { key: 'score', title: '得分', render: (row: MoleculeRelation) => row.score?.toFixed(3) ?? '—' },
                {
                  key: 'actions',
                  title: '操作',
                  render: (row: MoleculeRelation) => (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => row.id != null && handleDeleteRelation(row.id)}
                    >
                      删除
                    </Button>
                  ),
                },
              ]}
              data={relations}
            />
          </div>
        )}
      </Card>
    </div>
  )
}

// ============================================================================
// 批量去重
// ============================================================================

function DedupPanel({
  molecules,
  onComplete,
}: {
  molecules: MoleculeRecord[]
  onComplete: () => void
}) {
  const [threshold, setThreshold] = useState(0.95)
  const [result, setResult] = useState<DedupResult | null>(null)
  const [loading, setLoading] = useState(false)

  const handleDedup = async () => {
    if (molecules.length === 0) {
      showToast('分子库为空', 'warning')
      return
    }
    setLoading(true)
    try {
      const newMols: Array<[string, string]> = molecules.map((m) => [m.mol_id, m.esmiles])
      const res = await molDedupBatch(newMols, threshold)
      setResult(res)
      showToast(`去重完成: 发现 ${res.duplicates.length} 对重复`, 'success')
      onComplete()
    } catch (e) {
      showToast(`去重失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <AlertBanner
        variant="info"
        message="批量去重会对当前分子库中的所有分子进行两两比较，找出结构等价（Tanimoto ≥ 阈值）的分子对，并自动建立 same_as 关系。"
      />

      <Card>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ width: 260 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              等价阈值: {threshold.toFixed(2)}
            </div>
            <Slider min={0.8} max={1.0} step={0.01} value={threshold} onChange={(v) => setThreshold(v)} />
          </div>
          <Button variant="primary" size="sm" onClick={handleDedup} loading={loading}>
            执行去重
          </Button>
        </div>
      </Card>

      {result && (
        <Card>
          <SectionTitle>去重结果</SectionTitle>
          <ResponsiveStatGrid style={{ marginTop: 12 }}>
            <StatCard label="重复对" value={result.duplicates.length} />
            <StatCard label="新分子" value={result.new_mols.length} />
            <StatCard label="建立关系" value={result.relations_added} />
          </ResponsiveStatGrid>

          {result.duplicates.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <DataTable
                columns={[
                  { key: 'mol_a_id', title: '分子 A', width: 160 },
                  { key: 'mol_b_id', title: '分子 B', width: 160 },
                  { key: 'confidence', title: '置信度', render: (row) => `${(row.confidence * 100).toFixed(1)}%` },
                  { key: 'reason', title: '原因' },
                ]}
                data={result.duplicates}
              />
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
