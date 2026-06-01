// Dashboard mock 数据
// 真实项目应通过 API 拉取

export interface ProjectStats {
  documents: number
  molecules: number
  indexed: number
  conversations: number
  activeThisWeek: number
}

export interface ActivityDay {
  date: string
  value: number
}

export interface RecentActivity {
  id: string
  type: 'doc_indexed' | 'molecule_added' | 'chat_session' | 'search' | 'correction'
  title: string
  detail?: string
  timestamp: string
  actor?: string
}

export interface MoleculeStatus {
  pending: number
  confirmed: number
  corrected: number
  rejected: number
}

export const MOCK_STATS: ProjectStats = {
  documents: 142,
  molecules: 1284,
  indexed: 128,
  conversations: 47,
  activeThisWeek: 23,
}

// 过去 30 天的趋势（分子累计增长）
export const MOCK_GROWTH_TREND: number[] = [
  12, 18, 25, 31, 42, 58, 73, 89, 102, 120,
  145, 178, 210, 245, 289, 340, 398, 460, 520, 595,
  680, 760, 845, 935, 1020, 1100, 1180, 1220, 1255, 1284,
]

// 过去 7 天的对话数
export const MOCK_WEEKLY_CHATS = [
  { label: '周一', value: 4 },
  { label: '周二', value: 7 },
  { label: '周三', value: 5 },
  { label: '周四', value: 9 },
  { label: '周五', value: 6 },
  { label: '周六', value: 2 },
  { label: '周日', value: 3 },
]

// 12 周活动热力图
export function generateMockActivity(): ActivityDay[] {
  const days: ActivityDay[] = []
  const today = new Date()
  for (let i = 83; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    // 用伪随机模式：周末少，工作日多
    const dow = d.getDay()
    const isWeekend = dow === 0 || dow === 6
    const base = isWeekend ? 0 : 3
    const noise = Math.floor(Math.abs(Math.sin(i * 1.3)) * 6)
    days.push({
      date: d.toISOString().slice(0, 10),
      value: base + noise,
    })
  }
  return days
}

// 最近活动
export const MOCK_RECENT_ACTIVITY: RecentActivity[] = [
  {
    id: 'act_001',
    type: 'doc_indexed',
    title: '文献已索引',
    detail: 'paper_2024_cox2_inhibitors.pdf',
    timestamp: '2024-12-15T14:32:00Z',
    actor: 'auto-pipeline',
  },
  {
    id: 'act_002',
    type: 'molecule_added',
    title: '检测到 23 个新分子',
    detail: '来自 cox2_review.pdf',
    timestamp: '2024-12-15T14:28:00Z',
    actor: 'MolDet v2',
  },
  {
    id: 'act_003',
    type: 'correction',
    title: '手动矫正了 5 个分子',
    detail: 'Aspirin / Rofecoxib / ...',
    timestamp: '2024-12-15T13:45:00Z',
    actor: 'researcher',
  },
  {
    id: 'act_004',
    type: 'chat_session',
    title: '对话：COX-2 抑制剂 SAR',
    detail: '15 条消息',
    timestamp: '2024-12-15T11:20:00Z',
    actor: 'researcher',
  },
  {
    id: 'act_005',
    type: 'search',
    title: '搜索：IC50 < 100nM',
    detail: '返回 12 个结果',
    timestamp: '2024-12-15T10:15:00Z',
    actor: 'researcher',
  },
  {
    id: 'act_006',
    type: 'molecule_added',
    title: '检测到 8 个新分子',
    detail: '来自 celecoxib_synthesis.pdf',
    timestamp: '2024-12-14T16:42:00Z',
    actor: 'MolDet v2',
  },
  {
    id: 'act_007',
    type: 'doc_indexed',
    title: '文献已索引',
    detail: 'naproxen_metabolism.pdf',
    timestamp: '2024-12-14T15:30:00Z',
    actor: 'auto-pipeline',
  },
]

// 分子状态分布
export const MOCK_MOLECULE_STATUS: MoleculeStatus = {
  pending: 124,
  confirmed: 856,
  corrected: 218,
  rejected: 86,
}

// 文献分类分布
export const MOCK_DOC_CATEGORIES = [
  { label: '研究论文', value: 68, color: 'var(--accent)' },
  { label: '专利', value: 32, color: 'var(--success)' },
  { label: '综述', value: 24, color: 'var(--warning)' },
  { label: '临床报告', value: 12, color: 'var(--info)' },
  { label: '其他', value: 6, color: 'var(--text-muted)' },
]

// Top 活性分子（用于置顶区）
export const MOCK_TOP_MOLECULES = [
  { name: 'Valdecoxib', smiles: 'CC1=CC(=NO1)C1=CC=C(C=C1)S(N)(=O)=O', activity: 0.005, units: 'uM' },
  { name: 'Rofecoxib', smiles: 'CC1=C(C(=O)C2=CC=CC=C2O1)C1=CC=C(C=C1)OC', activity: 0.018, units: 'uM' },
  { name: 'Celecoxib', smiles: 'CC1=CC=C(C=C1)C1=CC(=NN1C1=CC=C(C=C1)S(N)(=O)=O)C(F)(F)F', activity: 0.06, units: 'uM' },
]
