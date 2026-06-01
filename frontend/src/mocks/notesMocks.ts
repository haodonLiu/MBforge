import type { Note, NoteLink } from '../components/notes/NoteEditor'

// ============================================================================
// Mock 笔记数据
// ============================================================================

export const MOCK_NOTES: Note[] = [
  {
    id: 'note_001',
    title: 'COX-2 抑制剂研究综述',
    content: `# COX-2 抑制剂研究综述

本笔记汇总 COX-2 选择性抑制剂的关键发现。详细内容见 [[Celecoxib 合成路线]] 与 [[SAR 矩阵分析]]。

## 核心发现

1. **Celecoxib** 是经典的 COX-2 选择性抑制剂
2. Rofecoxib 因心血管副作用已退市
3. 新一代抑制剂在尝试提高选择性比

## 活性数据

| 化合物 | IC50 (nM) | 选择性比 |
|--------|-----------|----------|
| Celecoxib | 60 | 7.6 |
| Rofecoxib | 18 | 35 |
| Valdecoxib | 5 | 30 |

## 关键文献

- 原始论文见文献库中的 paper_2024_cox2.pdf
- 综述：cox2_inhibitors_review.pdf
`,
    tags: ['综述', 'COX-2', '药物化学'],
    links: [
      { type: 'document', refId: 'paper_2024_cox2', refTitle: 'paper_2024_cox2.pdf' },
      { type: 'molecule', refId: 'cmp_001', refTitle: 'Celecoxib' },
    ],
    createdAt: '2024-12-01T10:00:00Z',
    updatedAt: '2024-12-15T14:30:00Z',
  },
  {
    id: 'note_002',
    title: '实验设计：分子对接方案',
    content: `# 分子对接实验设计

## 目标

通过 AutoDock Vina 对候选化合物与 COX-2 蛋白 (PDB: 5IKQ) 进行对接。

## 步骤

1. 蛋白准备：加氢、去水、加电荷
2. 配体准备：能量最小化、生成 3D 构象
3. 对接盒子：覆盖活性位点
4. 评分：Vina 评分函数

> 详细参数设置参见 [[对接参数参考]]
`,
    tags: ['实验', '对接', 'AutoDock'],
    links: [],
    createdAt: '2024-12-10T09:00:00Z',
    updatedAt: '2024-12-12T16:20:00Z',
  },
  {
    id: 'note_003',
    title: '会议纪要：12/14 项目讨论',
    content: `# 会议纪要 - 12/14

## 议程

- 上周进展回顾
- OCR 矫正流程优化
- 下周计划

## 关键决策

1. 同意采用 [[COX-2 抑制剂研究综述]] 中的 SAR 矩阵方案
2. OCR 矫正面板增加批量确认功能
3. 新增 R-Group 分析模块

## 待办

- [ ] 完成 Valdecoxib 矫正（@researcher）
- [ ] 上传新的 SAR 数据集（@researcher）
- [x] 修复 PubChem 渲染问题
`,
    tags: ['会议', 'TODO'],
    links: [],
    createdAt: '2024-12-14T15:00:00Z',
    updatedAt: '2024-12-14T17:00:00Z',
  },
  {
    id: 'note_004',
    title: 'Celecoxib 合成路线',
    content: `# Celecoxib 合成路线

## 概述

Celecoxib 通过三步反应合成：

1. 4-甲基苯乙酮 → 4-甲磺酰基苯乙酮
2. 缩合反应生成吡唑环
3. 与 4-氨基苯磺酰胺偶联

## 关键中间体

- **4-甲磺酰基苯乙酮**：起始原料
- **3-(4-甲磺酰基苯基)-5-对甲苯基吡唑**：关键中间体

## 产率

总产率约 65%。
`,
    tags: ['合成', 'Celecoxib'],
    links: [
      { type: 'note', refId: 'note_001', refTitle: 'COX-2 抑制剂研究综述' },
    ],
    createdAt: '2024-12-08T11:00:00Z',
    updatedAt: '2024-12-13T10:00:00Z',
  },
]

/** 双链候选（用于编辑器补全）*/
export const MOCK_WIKILINK_SUGGESTIONS: Array<{ id: string; title: string; type: NoteLink['type'] }> = [
  ...MOCK_NOTES.map(n => ({ id: n.id, title: n.title, type: 'note' as const })),
  { id: 'cmp_001', title: 'Celecoxib', type: 'molecule' as const },
  { id: 'cmp_002', title: 'Rofecoxib', type: 'molecule' as const },
  { id: 'paper_2024_cox2', title: 'paper_2024_cox2.pdf', type: 'document' as const },
]
