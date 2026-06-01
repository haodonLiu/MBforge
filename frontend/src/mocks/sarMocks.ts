import type { SARSession, SARCompound } from '../types'

// ============================================================================
// Mock SAR 数据集
// ============================================================================

/**
 * COX-2 抑制剂 SAR 数据集（经典药物化学案例）
 *
 * 来源：模拟数据，用于前端开发演示
 * 真实项目应通过 API 拉取
 */
export const MOCK_COX2_SAR: SARSession = {
  id: 'sar_demo_cox2_001',
  name: 'COX-2 选择性抑制剂',
  target: 'Cyclooxygenase-2 (COX-2)',
  coreSmiles: 'CC(=O)Oc1ccccc1C(=O)O',
  createdAt: '2024-12-01T10:00:00Z',
  sourceDocs: ['paper_2024_cox2.pdf', 'cox2_inhibitors_review.pdf'],
  compounds: [
    {
      id: 'cmp_001',
      name: 'Celecoxib',
      smiles: 'CC1=CC=C(C=C1)C1=CC(=NN1C1=CC=C(C=C1)S(N)(=O)=O)C(F)(F)F',
      rGroups: {},
      activity: 0.06,
      activityType: 'IC50',
      units: 'uM',
      notes: '阳性对照 / 上市药物',
    },
    {
      id: 'cmp_002',
      name: 'Rofecoxib',
      smiles: 'CC1=C(C(=O)C2=CC=CC=C2O1)C1=CC=C(C=C1)OC',
      rGroups: {},
      activity: 0.018,
      activityType: 'IC50',
      units: 'uM',
      notes: '阳性对照',
    },
    {
      id: 'cmp_003',
      name: 'Valdecoxib',
      smiles: 'CC1=CC(=NO1)C1=CC=C(C=C1)S(N)(=O)=O',
      rGroups: {},
      activity: 0.005,
      activityType: 'IC50',
      units: 'uM',
    },
    {
      id: 'cmp_004',
      name: 'Parecoxib',
      smiles: 'CC1=CC(=NO1)C1=CC=C(C=C1)S(=O)(=O)NC(=O)CC',
      rGroups: {},
      activity: 0.19,
      activityType: 'IC50',
      units: 'uM',
      selectivity: { 'COX-1/COX-2': 338 },
    },
    {
      id: 'cmp_005',
      name: 'Aspirin',
      smiles: 'CC(=O)Oc1ccccc1C(=O)O',
      rGroups: {},
      activity: 50,
      activityType: 'IC50',
      units: 'uM',
      notes: '非选择性 COX 抑制剂',
    },
    {
      id: 'cmp_006',
      name: 'Ibuprofen',
      smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
      rGroups: {},
      activity: 12,
      activityType: 'IC50',
      units: 'uM',
    },
    {
      id: 'cmp_007',
      name: 'Naproxen',
      smiles: 'COc1ccc2cc(C(C)C(=O)O)ccc2c1',
      rGroups: {},
      activity: 6.3,
      activityType: 'IC50',
      units: 'uM',
    },
    {
      id: 'cmp_008',
      name: 'Diclofenac',
      smiles: 'OC(=O)Cc1ccccc1Nc1c(Cl)cccc1Cl',
      rGroups: {},
      activity: 0.84,
      activityType: 'IC50',
      units: 'uM',
    },
  ],
}

/** Mock 矫正流程的样本数据 */
export const MOCK_CORRECTION_ITEMS = [
  {
    id: 'corr_001',
    ocrSmiles: 'CC1=CC=C(C=C1)C1=CC(=NN1C1=CC=C(C=C1)S(N)(=O)=O)C(F)(F)F',
    ocrConfidence: 0.92,
    name: 'Celecoxib',
    sourceDoc: 'paper_2024_cox2.pdf',
    context: 'In a screening campaign against COX-2, celecoxib showed an IC50 of 60 nM...',
    status: 'pending' as const,
  },
  {
    id: 'corr_002',
    ocrSmiles: 'CC1=C(C(=O)C2=CC=CC=C2O1)C1=CC=C(C=C1)OC', // 注：Rofecoxib 的实际 SMILES
    ocrConfidence: 0.76,
    name: 'Rofecoxib',
    sourceDoc: 'paper_2024_cox2.pdf',
    context: '...rofecoxib was identified as a potent and selective inhibitor (IC50 = 18 nM)...',
    status: 'pending' as const,
  },
  {
    id: 'corr_003',
    // 这个 OCR 识别有错误（漏了一个原子）
    ocrSmiles: 'CC(=O)Oc1ccccc1C(=O)', // 应为 'CC(=O)Oc1ccccc1C(=O)O'
    ocrConfidence: 0.45,
    name: 'Aspirin (可疑)',
    sourceDoc: 'cox2_inhibitors_review.pdf',
    context: 'Aspirin (acetylsalicylic acid) is a non-selective COX inhibitor with IC50 ≈ 50 μM...',
    status: 'pending' as const,
  },
  {
    id: 'corr_004',
    ocrSmiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
    ocrConfidence: 0.88,
    name: 'Ibuprofen',
    sourceDoc: 'cox2_inhibitors_review.pdf',
    context: '...ibuprofen exhibited moderate COX-2 inhibition with IC50 = 12 μM...',
    status: 'pending' as const,
  },
]

// ============================================================================
// API 占位（未来对接后端）
// ============================================================================

export async function fetchSARList(): Promise<SARSession[]> {
  // 模拟网络延迟
  await new Promise(r => setTimeout(r, 300))
  return [MOCK_COX2_SAR]
}

export async function fetchSARById(id: string): Promise<SARSession | null> {
  await new Promise(r => setTimeout(r, 200))
  return id === MOCK_COX2_SAR.id ? MOCK_COX2_SAR : null
}

export async function saveSARCompound(cmp: SARCompound): Promise<SARCompound> {
  await new Promise(r => setTimeout(r, 200))
  return cmp
}
