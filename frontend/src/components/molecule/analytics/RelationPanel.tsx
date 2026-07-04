import { useState, useEffect } from 'react'
import { showToast } from '../../../hooks/useToast'
import {
  molGetStats,
  molFindByMolecule,
  molAddRelation,
  molDeleteRelation,
} from '../../../api/http/molecule'
import type { RelationStats, MoleculeRelation } from '../../../api/http/molecule'
import type { MoleculeRecord } from '../../../types'
import { Card, Button, SectionTitle, Input, DataTable, Select, ResponsiveStatGrid, StatCard } from '../../ui'

export interface RelationPanelProps {
  molecules: MoleculeRecord[]
}

export default function RelationPanel({ molecules }: RelationPanelProps) {
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

  const molOptions = molecules.map((m) => ({
    value: m.mol_id,
    label: m.name || m.mol_id,
  }))

  const relTypeOptions = [
    { value: 'similar', label: '相似' },
    { value: 'same_as', label: '等价' },
    { value: 'scaffold', label: '骨架' },
    { value: 'cluster', label: '聚类' },
  ]

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
            <Select
              value={newRelA}
              onChange={setNewRelA}
              options={molOptions}
              placeholder="选择…"
            />
          </div>
          <div style={{ flex: 1, minWidth: 160 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>分子 B</div>
            <Select
              value={newRelB}
              onChange={setNewRelB}
              options={molOptions}
              placeholder="选择…"
            />
          </div>
          <div style={{ width: 140 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>类型</div>
            <Select
              value={newRelType}
              onChange={(v) => setNewRelType(v as typeof newRelType)}
              options={relTypeOptions}
            />
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
            <Select
              value={searchMolId}
              onChange={setSearchMolId}
              options={molOptions}
              placeholder="选择分子…"
            />
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
