import { useState } from 'react'
import { showToast } from '../../../hooks/useToast'
import { molSearchSubstructure } from '../../../api/http/molecule'
import type { SubstructureMatch } from '../../../api/http/molecule'
import { Card, Input, Slider, Button, DataTable } from '../../ui'

export default function SubstructureSearchPanel() {
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
