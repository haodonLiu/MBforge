import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { motion } from 'framer-motion'
import { PageContainer, PageTitle, Card, Button, Badge, SectionTitle, ResponsiveStatGrid, EmptyState } from './ui'
import {
  FileTextIcon, FlaskIcon, ChatIcon, SparklesIcon,
  ExternalLinkIcon, RefreshCwIcon,
} from './icons'
import MoleculeDisplay from './molecule/MoleculeDisplay'
import Sparkline from './dashboard/Sparkline'
import { showToast } from '../hooks/useToast'
import { fadeUp } from '../hooks/useAnimations'
import { useAppContext } from '../context/AppContext'
import { listProjectDocuments } from '../api/tauri/project'
import { moleculeStatsTauri, listMoleculesTauri } from '../api/tauri/molecule'
import type { MoleculeRecord } from '../types'



// ============================================================================
// 顶部 StatCard
// ============================================================================

interface StatCardProps {
  label: string
  value: number | string
  delta?: number
  subValue?: string
  icon: React.ReactNode
  color: string
  trend?: number[]
  delay?: number
}

function StatCard({ label, value, delta, subValue, icon, color, trend, delay = 0 }: StatCardProps) {
  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      animate="visible"
      transition={{ delay }}
    >
      <Card hoverable style={{ padding: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: color + '20', color,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {icon}
          </div>
          {delta !== undefined && (
            <Badge variant={delta >= 0 ? 'success' : 'danger'}>
              {delta >= 0 ? '+' : ''}{delta}%
            </Badge>
          )}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
          {label}
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginTop: 4 }}>
          {value.toLocaleString()}
        </div>
        {subValue && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{subValue}</div>
        )}
        {trend && trend.length > 0 && (
          <div style={{ marginTop: 12, marginLeft: -4 }}>
            <Sparkline
              data={trend}
              width="100%"
              height={36}
              color={color}
              fillColor={color}
              showDots={false}
            />
          </div>
        )}
      </Card>
    </motion.div>
  )
}



// ============================================================================
// 主页面
// ============================================================================

interface DashboardStats {
  documents: number
  indexed: number
  molecules: number
  confirmed: number
  conversations: number
  activeThisWeek: number
}

export default function Dashboard() {
  const { t } = useTranslation()
  const { projectRoot } = useAppContext()
  const [stats, setStats] = useState<DashboardStats>({
    documents: 0, indexed: 0, molecules: 0, confirmed: 0, conversations: 0, activeThisWeek: 0,
  })
  const [topMolecules, setTopMolecules] = useState<MoleculeRecord[]>([])
  const [refreshing, setRefreshing] = useState(false)
  const [loading, setLoading] = useState(true)

  const loadData = async () => {
    if (!projectRoot) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const [docResp, molResp, molListResp] = await Promise.all([
        listProjectDocuments(projectRoot).catch(() => ({ documents: [] })),
        moleculeStatsTauri(projectRoot).catch(() => ({ success: false, stats: { total: 0, pending: 0 } })),
        listMoleculesTauri(projectRoot, 3, 0).catch(() => ({ success: false, molecules: [] })),
      ])

      const docs = docResp.documents ?? []
      const indexed = docs.filter((d: { indexed: boolean }) => d.indexed).length
      const molStats = molResp.success ? molResp.stats : { total: 0, pending: 0 }

      setStats({
        documents: docs.length,
        indexed,
        molecules: molStats.total ?? 0,
        confirmed: (molStats.total ?? 0) - (molStats.pending ?? 0),
        conversations: 0,
        activeThisWeek: 0,
      })

      const molecules = (molListResp.success ? molListResp.molecules : [])
        .filter((m: MoleculeRecord) => m.activity != null)
        .sort((a: MoleculeRecord, b: MoleculeRecord) => (a.activity ?? 0) - (b.activity ?? 0))
        .slice(0, 3)
      setTopMolecules(molecules)
    } catch (e) {
      showToast('加载仪表盘数据失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [projectRoot])

  const handleRefresh = async () => {
    setRefreshing(true)
    await loadData()
    setRefreshing(false)
    showToast('数据已刷新', 'success')
  }

  if (loading) {
    return (
      <PageContainer>
        <PageTitle>Dashboard</PageTitle>
        <EmptyState message="正在加载项目数据..." />
      </PageContainer>
    )
  }

  if (!projectRoot) {
    return (
      <PageContainer>
        <PageTitle>Dashboard</PageTitle>
        <EmptyState message="请先打开或创建一个项目以查看仪表盘" />
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      {/* 顶部 */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24, gap: 16, flexWrap: 'wrap' }}>
        <div>
          <PageTitle>Dashboard</PageTitle>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
            项目全景概览 · 数据每 5 分钟自动更新
          </div>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleRefresh}
          loading={refreshing}
        >
          <RefreshCwIcon size={14} /> 刷新
        </Button>
      </div>

      {/* Stat Cards */}
      <ResponsiveStatGrid style={{ marginBottom: 24 }}>
        <StatCard
          label="文献总数"
          value={stats.documents}
          subValue={`${stats.indexed} 已索引`}
          icon={<FileTextIcon size={18} />}
          color="var(--info)"
        />
        <StatCard
          label="分子总数"
          value={stats.molecules}
          subValue={`${stats.confirmed} ${t('dashboard.confirmed')}`}
          icon={<FlaskIcon size={18} />}
          color="var(--accent)"
          delay={0.05}
        />
        <StatCard
          label={t('dashboard.conversations')}
          value={stats.conversations}
          subValue={t('dashboard.weekActive')}
          icon={<ChatIcon size={18} />}
          color="var(--success)"
          delay={0.1}
        />
        <StatCard
          label="本周操作"
          value={stats.activeThisWeek}
          subValue="次"
          icon={<SparklesIcon size={18} />}
          color="var(--warning)"
          delay={0.15}
        />
      </ResponsiveStatGrid>

      {/* 主要面板：2 列布局 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', gap: 16, marginBottom: 16 }}>
        {/* Top 活性分子 */}
        <Card padding="20px">
          <SectionTitle style={{ marginBottom: 16 }}>
            高活性分子
          </SectionTitle>
          {topMolecules.length === 0 ? (
            <EmptyState message="暂无带活性数据的分子" />
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
              {topMolecules.map(mol => (
                <Card key={mol.mol_id} padding="12px" style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  flexDirection: 'row',
                }}>
                  <MoleculeDisplay
                    smiles={mol.esmiles}
                    name={mol.name || mol.mol_id}
                    size={80}
                    showMetadata={false}
                    mode="view"
                    style={{ border: 'none', padding: 0, background: 'transparent', flexShrink: 0 }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                      {mol.name || mol.mol_id}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--success)', fontWeight: 600 }}>
                      {mol.activity_type || 'Activity'} = {mol.activity?.toFixed(3)} {mol.units || ''}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => showToast(`打开 ${mol.name || mol.mol_id} 详情`, 'info')}
                      style={{ marginTop: 6, padding: '2px 8px', fontSize: 11 }}
                    >
                      详情 <ExternalLinkIcon size={10} />
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </Card>

        {/* 项目概览 */}
        <Card padding="20px">
          <SectionTitle style={{ marginBottom: 16 }}>
            项目概览
          </SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {[
            ['项目路径', projectRoot, 'var(--text-primary)', 500],
            ['文献数', stats.documents, 'var(--text-primary)', 600],
            ['已索引', stats.indexed, 'var(--success)', 600],
            ['分子数', stats.molecules, 'var(--accent)', 600],
            ['已确认', stats.confirmed, 'var(--info)', 600],
          ].map(([label, value, color, weight]) => (
            <div key={String(label)} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
              <span style={{ color: 'var(--text-muted)' }}>{String(label)}</span>
              <span style={{ color: String(color), fontWeight: weight as number, wordBreak: label === '项目路径' ? 'break-all' as const : undefined, textAlign: label === '项目路径' ? 'right' as const : undefined }}>
                {String(value)}
              </span>
            </div>
          ))}
          </div>
        </Card>
      </div>
    </PageContainer>
  )
}
