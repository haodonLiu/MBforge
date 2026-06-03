import { useState, useEffect } from 'react'
import { RefreshCwIcon } from './icons'
import { PageContainer, PageTitle, Button } from './ui'
import ResponsiveStatGrid from './ui/ResponsiveStatGrid'
import StatCard from './workflow/StatCard'
import LibrarySection, { type CapabilityStatus } from './workflow/LibrarySection'
import {
  LoadingSkeleton,
  PathSection,
  ModelsSection,
} from './workflow/sections'
import type { ModelInfo, ModelPaths } from './workflow/types'

interface EnvironmentCheckResult {
  python_version: string
  gpu_available: boolean
  gpu_name: string | null
  gpu_memory_mb: number | null
  cuda_version: string | null
  capabilities: CapabilityStatus[]
}

/**
 * Environment 页面 — 展示 Python/GPU 环境、库依赖状态、模型缓存路径与已下载模型.
 *
 * 子组件：
 * - <StatCard>           关键指标 (Python 版本、GPU、显存、模型)
 * - <LibrarySection>     库分类 (core/md/docking/admet)
 * - <PathSection>        缓存目录区块
 * - <ModelsSection>      模型列表区块
 * - <LoadingSkeleton>    首屏占位
 */
export default function Environment() {
  const [env, setEnv] = useState<EnvironmentCheckResult | null>(null)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [paths, setPaths] = useState<ModelPaths | null>(null)
  const [loading, setLoading] = useState(true)
  const [editingPath, setEditingPath] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  const fetchEnv = () => {
    setLoading(true)
    fetch('/api/v1/environment/check')
      .then(r => r.json())
      .then(setEnv)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  const fetchModels = () => {
    fetch('/api/v1/download/models')
      .then(r => r.json())
      .then(data => {
        if (data.success) setModels(data.models)
      })
      .catch(console.error)
  }

  const fetchPaths = () => {
    fetch('/api/v1/download/model-paths')
      .then(r => r.json())
      .then(data => {
        if (data.success) setPaths(data.paths)
      })
      .catch(console.error)
  }

  const downloadModel = async (modelId: string) => {
    try {
      const response = await fetch(`/api/v1/download/${modelId}`, { method: 'POST' })
      if (response.ok) {
        const checkStatus = setInterval(() => {
          fetchModels()
        }, 2000)
        setTimeout(() => clearInterval(checkStatus), 30000)
      }
    } catch (e) {
      console.error('Download error:', e)
    }
  }

  const deleteModel = async (modelId: string) => {
    if (!confirm('Are you sure you want to delete this model?')) return
    try {
      const response = await fetch(`/api/v1/download/delete/${modelId}`, {
        method: 'DELETE',
      })
      const result = await response.json()
      if (result.success) {
        fetchModels()
      } else {
        console.error('Delete failed:', result.error)
      }
    } catch (e) {
      console.error('Delete error:', e)
    }
  }

  const savePath = async () => {
    if (!editValue.trim()) return
    try {
      const response = await fetch('/api/v1/download/model-dir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: editValue.trim() }),
      })
      const result = await response.json()
      if (result.success) {
        setEditingPath(null)
        fetchPaths()
        alert('Path updated! Please restart the app for changes to take effect.')
      } else {
        alert('Failed to update path: ' + result.error)
      }
    } catch (e) {
      console.error('Save path error:', e)
    }
  }

  useEffect(() => {
    fetchEnv()
    fetchModels()
    fetchPaths()
  }, [])

  if (loading && !env) {
    return <LoadingSkeleton />
  }

  if (!env) {
    return (
      <PageContainer>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '80px',
            color: 'var(--danger)',
          }}
        >
          Failed to get environment info
        </div>
      </PageContainer>
    )
  }

  // 按分类分组
  const coreLibs = env.capabilities.filter(c => c.category === 'core')
  const mdLibs = env.capabilities.filter(c => c.category === 'md')
  const dockingLibs = env.capabilities.filter(c => c.category === 'docking')
  const admetLibs = env.capabilities.filter(c => c.category === 'admet')

  // 模型统计
  const downloadedModels = models.filter(m => m.downloaded).length
  const totalDownloadedMB = models
    .filter(m => m.downloaded)
    .reduce((sum, m) => sum + m.actual_size_mb, 0)
  const totalEstimatedMB = models.reduce((sum, m) => sum + m.size_mb, 0)

  return (
    <PageContainer>
      {/* 标题栏 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '24px',
        }}
      >
        <PageTitle>Environment</PageTitle>
        <Button
          variant="secondary"
          icon={<RefreshCwIcon size={14} />}
          onClick={() => {
            fetchEnv()
            fetchModels()
            fetchPaths()
          }}
        >
          Refresh
        </Button>
      </div>

      {/* 统计卡片 */}
      <ResponsiveStatGrid style={{ marginBottom: '24px' }}>
        <StatCard label="Python" value={env.python_version} />
        <StatCard
          label="GPU"
          value={env.gpu_name?.split(' ').slice(0, 2).join(' ') || 'None'}
          subValue={env.cuda_version ? `CUDA ${env.cuda_version}` : undefined}
          variant={env.gpu_available ? 'success' : 'default'}
        />
        <StatCard
          label="GPU Memory"
          value={env.gpu_memory_mb ? `${Math.round(env.gpu_memory_mb / 1024)}GB` : 'N/A'}
        />
        <StatCard
          label="Models"
          value={`${downloadedModels}/${models.length}`}
          subValue={
            downloadedModels > 0
              ? `${Math.round(totalDownloadedMB)} MB / ${totalEstimatedMB} MB`
              : undefined
          }
          variant={downloadedModels === models.length && models.length > 0 ? 'success' : 'default'}
        />
      </ResponsiveStatGrid>

      {/* 库列表 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '24px' }}>
        <LibrarySection title="Core Libraries" libs={coreLibs} />
        {mdLibs.length > 0 && <LibrarySection title="Molecular Dynamics" libs={mdLibs} />}
        {dockingLibs.length > 0 && <LibrarySection title="Docking" libs={dockingLibs} />}
        {admetLibs.length > 0 && <LibrarySection title="ADMET" libs={admetLibs} />}
      </div>

      {/* 路径 + 模型 */}
      <PathSection
        paths={paths}
        editingPath={editingPath}
        editValue={editValue}
        onEdit={(name, p) => {
          setEditingPath(name)
          setEditValue(p)
        }}
        onSave={savePath}
        onCancel={() => setEditingPath(null)}
        onChange={setEditValue}
      />

      <ModelsSection
        models={models}
        downloadedCount={downloadedModels}
        onDownload={downloadModel}
        onDelete={deleteModel}
      />
    </PageContainer>
  )
}
