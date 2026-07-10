import { useState, useEffect } from 'react'
import { showToast } from '@/hooks/useToast'
import {
  molListClusters,
  molGetClusterMembers,
  molAssignCluster,
  molRemoveFromCluster,
} from '@/api/http/molecule'
import type { ClusterInfo } from '@/api/http/molecule'
import type { MoleculeRecord } from '@/types'
import { Card, Button, SectionTitle, Input, Select } from '../../ui'

export interface ClusterPanelProps {
  molecules: MoleculeRecord[]
}

export default function ClusterPanel({ molecules }: ClusterPanelProps) {
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
    void loadClusters()
  }, [])

  const handleAssign = async () => {
    if (!assignMolId || !assignClusterId) return
    try {
      await molAssignCluster(assignMolId, assignClusterId)
      showToast('聚类分配成功', 'success')
      void loadClusters()
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
      void loadClusters()
      if (selectedCluster?.cluster_id === clusterId) {
        const updated = await molGetClusterMembers(clusterId)
        setSelectedCluster(updated)
      }
    } catch (e) {
      showToast(`移除失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  const molOptions = molecules.map((m) => ({
    value: m.mol_id,
    label: m.name || m.mol_id,
  }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              分子 ID
            </div>
            <Select
              value={assignMolId}
              onChange={setAssignMolId}
              options={molOptions}
              placeholder="选择分子…"
            />
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
              } catch {
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
