import { useState, useEffect } from 'react'
import { showToast } from '../hooks/useToast'
import { RefreshCwIcon } from './icons'
import { PageContainer, PageTitle, Button, ScrollColumn } from './ui'
import ResponsiveStatGrid from './ui/ResponsiveStatGrid'
import StatCard from './environment/StatCard'
import LibrarySection, { type CapabilityStatus } from './environment/LibrarySection'
import {
  LoadingSkeleton,
  PathSection,
  ModelsSection,
} from './environment/sections'
import DetectionCacheCard from './settings/DetectionCacheCard'
import SidecarCard from './settings/SidecarCard'
import type { ModelInfo, ModelPaths } from './environment/types'
import { resourcesCatalog, resourcesStatus, modelsCacheDirInfo, refreshResolvedPaths } from '../api/tauri/environment'
import { downloadModel, deleteModel } from '../api/tauri/download'
import { saveSettings } from '../api/tauri/settings'
import { environmentCheck } from '../api/tauri/sidecar'

interface EnvironmentCheckResult {
  python_version: string
  gpu_available: boolean
  gpu_name: string | null
  gpu_memory_mb: number | null
  cuda_version: string | null
  capabilities: CapabilityStatus[]
}

interface CatalogItem {
  id: string
  name: string
  type: string
  description: string
  size_mb: number
  license: string
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

  const fetchEnv = async () => {
    setLoading(true)
    try {
      const data = await environmentCheck()
      setEnv(data as EnvironmentCheckResult)
    } catch {
      showToast('Python sidecar 未启动，Environment 页面不可用', 'warning')
      setEnv(null)
    } finally {
      setLoading(false)
    }
  }

  const fetchModels = async () => {
    try {
      const catalog = await resourcesCatalog()
      const modelItems = (catalog as unknown as CatalogItem[]).filter((item) => item.type === 'model')

      const models = await Promise.all(
        modelItems.map(async (item) => {
          const status = await resourcesStatus(item.id)
          return {
            id: item.id,
            name: item.name,
            type: item.type,
            description: item.description,
            downloaded: status.status === 'ready',
            downloading: false,
            size_mb: item.size_mb,
            actual_size_mb: status.size_mb || 0,
            license: item.license,
            location: {
              found: status.status === 'ready',
              primary: status.status === 'ready' ? 'modelscope' as const : null,
              locations: status.status === 'ready'
                ? [{ source: 'modelscope' as const, path: status.local_path, size_mb: status.size_mb }]
                : [],
            },
          }
        }),
      )

      setModels(models)
    } catch {
      showToast('获取模型列表失败', 'warning')
      setModels([])
    }
  }

  const fetchPaths = async () => {
    try {
      const info = await modelsCacheDirInfo()
      setPaths(info)
    } catch {
      showToast('获取模型路径失败', 'warning')
      setPaths(null)
    }
  }

  const handleDownloadModel = (modelId: string) => {
    try {
      let completed = false
      const cancel = downloadModel(modelId, (progress) => {
        if (progress.status === 'completed' || progress.status === 'failed') {
          completed = true
          void fetchModels()
        }
      })
      setTimeout(() => {
        cancel()
        if (!completed) void fetchModels()
      }, 30000)
    } catch (e) {
      showToast(`Download failed: ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  const handleDeleteModel = async (modelId: string) => {
    if (!confirm('Are you sure you want to delete this model?')) return
    try {
      await deleteModel(modelId)
      void fetchModels()
    } catch (e) {
      showToast(`Delete failed: ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  const handleRefreshModelEnv = async () => {
    try {
      await refreshResolvedPaths()
      showToast('模型环境已更新', 'success')
      await fetchEnv()
      await fetchModels()
      await fetchPaths()
    } catch (e) {
      showToast(`刷新模型环境失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  const savePath = async () => {
    if (!editValue.trim()) return
    try {
      const result = await saveSettings({ model_cache_dir: editValue.trim() })
      if (result.success) {
        setEditingPath(null)
        void fetchPaths()
        showToast('Path updated! Please restart the app for changes to take effect.', 'info')
      } else {
        showToast(`Failed to update path: ${result.error}`, 'error')
      }
    } catch (e) {
      showToast(`Save path failed: ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  useEffect(() => {
    void fetchEnv()
    void fetchModels()
    void fetchPaths()
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
          onClick={handleRefreshModelEnv}
        >
          刷新模型环境
        </Button>
      </div>

      {/* 滚动区 — ScrollColumn 提供 flex:1 + minHeight:0 + overflowY:auto
          三件套，否则 PageContainer 的 overflow:hidden 会把内容切掉。 */}
      <ScrollColumn>
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

        {/* 路径 */}
        <div style={{ marginBottom: '24px' }}>
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
        </div>

        {/* 模型列表 */}
        <div style={{ marginBottom: '24px' }}>
          <ModelsSection
            models={models}
            downloadedCount={downloadedModels}
            onDownload={handleDownloadModel}
            onDelete={handleDeleteModel}
          />
        </div>

        {/* 分子检测缓存（detection cache）—— 之前在 Settings → diagnostics 里，
            重复了 Environment 的资源检查，迁过来统一管理 */}
        <div style={{ marginBottom: '24px' }}>
          <DetectionCacheCard />
        </div>

        {/* Sidecar (Python FastAPI) 健康监控 + 手动重启 */}
        <div style={{ marginBottom: '24px' }}>
          <SidecarCard />
        </div>
      </ScrollColumn>
    </PageContainer>
  )
}
