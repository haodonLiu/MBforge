import { useState } from 'react'
import { showToast } from '../../../hooks/useToast'
import { molFindAnalogsWithActivity } from '../../../api/http/molecule'
import type { AnalogWithActivity } from '../../../api/http/molecule'
import type { MoleculeRecord } from '../../../types'
import { Card, Slider, Button, DataTable, Select } from '../../ui'

export interface AnalogSearchPanelProps {
  molecules: MoleculeRecord[]
}

export default function AnalogSearchPanel({ molecules }: AnalogSearchPanelProps) {
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

  const selectOptions = molecules.map((m) => ({
    value: m.mol_id,
    label: `${m.name || m.mol_id} (${m.esmiles.slice(0, 30)}…)`,
  }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              参考分子 ID
            </div>
            <Select
              value={selectedId}
              onChange={setSelectedId}
              options={selectOptions}
              placeholder="选择分子…"
            />
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
