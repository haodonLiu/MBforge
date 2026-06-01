import { useEffect, useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { PageContainer, PageTitle, Card, Button, Badge, ResponsiveStatGrid } from './ui'
import {
  FileTextIcon, FlaskIcon, ChatIcon, BarChartIcon, SparklesIcon,
  ExternalLinkIcon, RefreshCwIcon, ArrowLeftIcon, ClockIcon,
} from './icons'
import Sparkline, { BarChart, DonutChart, Heatmap } from './dashboard/Sparkline'
import MoleculeDisplay from './molecule/MoleculeDisplay'
import {
  MOCK_STATS, MOCK_GROWTH_TREND, MOCK_WEEKLY_CHATS,
  generateMockActivity, MOCK_RECENT_ACTIVITY, MOCK_MOLECULE_STATUS,
  MOCK_DOC_CATEGORIES, MOCK_TOP_MOLECULES,
  type ActivityDay, type RecentActivity,
} from '../mocks/dashboardMocks'
import { showToast } from '../hooks/useToast'
import { fadeUp } from '../hooks/useAnimations'

// ============================================================================
// 时间格式化
// ============================================================================

function relativeTime(iso: string): string {
  const now = Date.now()
  const t = new Date(iso).getTime()
  const diff = (now - t) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`
  return new Date(iso).toLocaleDateString('zh-CN')
}

const activityTypeMap: Record<RecentActivity['type'], { label: string; color: string; iconType: 'doc' | 'mol' | 'chat' | 'search' | 'fix' }> = {
  doc_indexed:    { label: '文献',   color: 'var(--info)',    iconType: 'doc' },
  molecule_added: { label: '分子',   color: 'var(--accent)',  iconType: 'mol' },
  chat_session:   { label: '对话',   color: 'var(--success)', iconType: 'chat' },
  search:         { label: '搜索',   color: 'var(--text-muted)', iconType: 'search' },
  correction:     { label: '矫正',   color: 'var(--warning)', iconType: 'fix' },
}

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
// 活动项
// ============================================================================

function ActivityItem({ item }: { item: RecentActivity }) {
  const meta = activityTypeMap[item.type]
  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-start',
      gap: 12,
      padding: '10px 0',
      borderBottom: '1px solid var(--border)',
    }}>
      <div style={{
        width: 32, height: 32, borderRadius: 8,
        background: meta.color + '20', color: meta.color,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        {meta.iconType === 'doc' && <FileTextIcon size={16} />}
        {meta.iconType === 'mol' && <FlaskIcon size={16} />}
        {meta.iconType === 'chat' && <ChatIcon size={16} />}
        {meta.iconType === 'search' && <BarChartIcon size={16} />}
        {meta.iconType === 'fix' && <SparklesIcon size={16} />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
          <Badge variant="neutral">{meta.label}</Badge>
          <span style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>{item.title}</span>
        </div>
        {item.detail && (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {item.detail}
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, fontSize: 11, color: 'var(--text-muted)' }}>
          <ClockIcon size={11} />
          <span>{relativeTime(item.timestamp)}</span>
          {item.actor && <span>· {item.actor}</span>}
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// 主页面
// ============================================================================

export default function Dashboard() {
  const [activity, setActivity] = useState<ActivityDay[]>([])
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    setActivity(generateMockActivity())
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    await new Promise(r => setTimeout(r, 600))
    setActivity(generateMockActivity())
    setRefreshing(false)
    showToast('数据已刷新', 'success')
  }

  // 计算本周 vs 上周增量（mock）
  const weeklyDelta = useMemo(() => {
    return {
      molecules: 12,
      documents: 4,
      conversations: 18,
      indexed: 8,
    }
  }, [])

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
          value={MOCK_STATS.documents}
          delta={weeklyDelta.documents}
          subValue={`${MOCK_STATS.indexed} 已索引`}
          icon={<FileTextIcon size={18} />}
          color="var(--info)"
          trend={[5, 8, 12, 18, 25, 35, 48, 65, 80, 102, 128]}
        />
        <StatCard
          label="分子总数"
          value={MOCK_STATS.molecules}
          delta={weeklyDelta.molecules}
          subValue={`${MOCK_MOLECULE_STATUS.confirmed} 已确认`}
          icon={<FlaskIcon size={18} />}
          color="var(--accent)"
          trend={MOCK_GROWTH_TREND.slice(-12)}
          delay={0.05}
        />
        <StatCard
          label="对话数"
          value={MOCK_STATS.conversations}
          delta={weeklyDelta.conversations}
          subValue="本周活跃"
          icon={<ChatIcon size={18} />}
          color="var(--success)"
          trend={[2, 4, 5, 7, 9, 6, 8, 12, 15, 13, 18, 22]}
          delay={0.1}
        />
        <StatCard
          label="本周操作"
          value={MOCK_STATS.activeThisWeek}
          subValue="次"
          icon={<SparklesIcon size={18} />}
          color="var(--warning)"
          trend={[3, 5, 8, 12, 15, 18, 23]}
          delay={0.15}
        />
      </ResponsiveStatGrid>

      {/* 主要面板：2 列布局 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', gap: 16, marginBottom: 16 }}>
        {/* 趋势图 */}
        <Card style={{ padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>分子累计增长</h3>
              <p style={{ margin: '2px 0 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                过去 30 天
              </p>
            </div>
            <Badge variant="success" dot>趋势上升</Badge>
          </div>
          <Sparkline
            data={MOCK_GROWTH_TREND}
            width="100%"
            height={180}
            color="var(--accent)"
            fillColor="var(--accent)"
            strokeWidth={2.5}
            showGrid
            smooth
          />
        </Card>

        {/* 文档分布 */}
        <Card style={{ padding: 20 }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: 15, fontWeight: 600 }}>文献分类</h3>
          <DonutChart data={MOCK_DOC_CATEGORIES} size={140} thickness={18} />
        </Card>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr)', gap: 16, marginBottom: 16 }}>
        {/* 周对话柱状图 */}
        <Card style={{ padding: 20 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 15, fontWeight: 600 }}>本周对话</h3>
          <BarChart
            data={MOCK_WEEKLY_CHATS}
            width="100%"
            height={160}
            highlightLast
            barColor="var(--success)"
          />
        </Card>

        {/* 分子状态 */}
        <Card style={{ padding: 20 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 15, fontWeight: 600 }}>分子状态</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {Object.entries(MOCK_MOLECULE_STATUS).map(([key, val]) => {
              const meta = {
                pending:   { label: '待处理', color: 'var(--warning)' },
                confirmed: { label: '已确认', color: 'var(--success)' },
                corrected: { label: '已修正', color: 'var(--info)' },
                rejected:  { label: '已拒绝', color: 'var(--danger)' },
              }[key]!
              const pct = (val / MOCK_STATS.molecules) * 100
              return (
                <div key={key}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                    <span style={{ color: 'var(--text-secondary)' }}>{meta.label}</span>
                    <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{val}</span>
                  </div>
                  <div style={{ height: 6, background: 'var(--bg-elevated)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ width: `${pct}%`, height: '100%', background: meta.color, borderRadius: 3 }} />
                  </div>
                </div>
              )
            })}
          </div>
        </Card>

        {/* 活动热力图 */}
        <Card style={{ padding: 20 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 15, fontWeight: 600 }}>活动热力图</h3>
          <p style={{ margin: '0 0 12px 0', fontSize: 11, color: 'var(--text-muted)' }}>
            过去 12 周每日操作数
          </p>
          <div style={{ overflowX: 'auto' }}>
            <Heatmap data={activity} days={84} />
          </div>
        </Card>
      </div>

      {/* 底部：Top 分子 + 最近活动 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', gap: 16 }}>
        {/* Top 活性分子 */}
        <Card style={{ padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>高活性分子</h3>
              <p style={{ margin: '2px 0 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                按 IC50 排序 · 前 3
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={() => showToast('查看全部功能开发中', 'info')}>
              查看全部
            </Button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
            {MOCK_TOP_MOLECULES.map(mol => (
              <div key={mol.name} style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: 12,
                background: 'var(--bg-base)',
                borderRadius: 8,
                border: '1px solid var(--border)',
              }}>
                <MoleculeDisplay
                  smiles={mol.smiles}
                  name={mol.name}
                  size={80}
                  showMetadata={false}
                  mode="view"
                  style={{ border: 'none', padding: 0, background: 'transparent', flexShrink: 0 }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                    {mol.name}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--success)', fontWeight: 600 }}>
                    IC50 = {mol.activity} {mol.units}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => showToast(`打开 ${mol.name} 详情`, 'info')}
                    style={{ marginTop: 6, padding: '2px 8px', fontSize: 11 }}
                  >
                    详情 <ExternalLinkIcon size={10} />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* 最近活动 */}
        <Card style={{ padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>最近活动</h3>
            <Button variant="ghost" size="sm" onClick={() => showToast('完整活动时间线开发中', 'info')}>
              <ArrowLeftIcon size={12} /> 更多
            </Button>
          </div>
          <div>
            {MOCK_RECENT_ACTIVITY.slice(0, 6).map(item => (
              <ActivityItem key={item.id} item={item} />
            ))}
          </div>
        </Card>
      </div>
    </PageContainer>
  )
}
