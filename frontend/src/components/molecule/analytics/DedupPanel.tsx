import { useState } from 'react'
import { showToast } from '../../../hooks/useToast'
import { molDedupBatch } from '../../../api/tauri/molecule'
import type { DedupResult } from '../../../api/tauri/molecule'
import type { MoleculeRecord } from '../../../types'
import { Card, Button, Slider, SectionTitle, AlertBanner, ResponsiveStatGrid, StatCard, DataTable } from '../../ui'

export interface DedupPanelProps {
  molecules: MoleculeRecord[]
  onComplete: () => void
}

export default function DedupPanel({ molecules, onComplete }: DedupPanelProps) {
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
