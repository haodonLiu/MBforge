import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { ask } from '@tauri-apps/plugin-dialog'
import { RefreshCwIcon } from '@/components/icons'
import { Button, SectionTitle } from '@/components/ui'
import ResponsiveStatGrid from '@/components/ui/ResponsiveStatGrid'
import StatCard from '@/components/environment/StatCard'
import LibrarySection, { type CapabilityStatus } from '@/components/environment/LibrarySection'
import {
  PathSection,
  ModelsSection,
} from '@/components/environment/sections'
import DetectionCacheCard from '@/components/settings/DetectionCacheCard'
import SidecarCard from '@/components/settings/SidecarCard'
import ModelServiceSection from '@/components/settings/sections/ModelServiceSection'
import type { ModelInfo, ModelPaths } from '@/components/environment/types'
import { resourcesCatalog, resourcesStatus, modelsCacheDirInfo, refreshResolvedPaths } from '@/api/tauri/environment'
import { downloadModel, deleteModel } from '@/api/tauri/download'
import { saveSettings } from '@/api/tauri/settings'
import { environmentCheck } from '@/api/tauri/sidecar'
import { showToast } from '@/hooks/useToast'
import type { SettingsState } from '@/components/settings/types'

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

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

export default function SystemTab({ settings, setSettings }: Props) {
  const { t } = useTranslation()
  const [env, setEnv] = useState<EnvironmentCheckResult | null>(null)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [paths, setPaths] = useState<ModelPaths | null>(null)
  const [loading, setLoading] = useState(true)
  const [editingPath, setEditingPath] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  const fetchEnv = useCallback(async () => {
    setLoading(true)
    try {
      const data = await environmentCheck()
      setEnv(data as EnvironmentCheckResult)
    } catch {
      showToast(t('systemTab.loadEnvFailed'), 'warning')
      setEnv(null)
    } finally {
      setLoading(false)
    }
  }, [t])

  const fetchModels = useCallback(async () => {
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
      showToast(t('systemTab.loadModelsFailed'), 'warning')
      setModels([])
    }
  }, [t])

  const fetchPaths = useCallback(async () => {
    try {
      const info = await modelsCacheDirInfo()
      setPaths(info)
    } catch {
      showToast(t('systemTab.loadPathsFailed'), 'warning')
      setPaths(null)
    }
  }, [t])

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
      showToast(t('systemTab.downloadFailed', { error: e instanceof Error ? e.message : String(e) }), 'error')
    }
  }

  const handleDeleteModel = async (modelId: string) => {
    const ok = await ask(t('systemTab.confirmDelete'), { kind: 'warning' })
    if (!ok) return
    try {
      await deleteModel(modelId)
      void fetchModels()
    } catch (e) {
      showToast(t('systemTab.deleteFailed', { error: e instanceof Error ? e.message : String(e) }), 'error')
    }
  }

  const handleRefreshModelEnv = async () => {
    try {
      await refreshResolvedPaths()
      showToast(t('systemTab.refreshSuccess'), 'success')
      await fetchEnv()
      await fetchModels()
      await fetchPaths()
    } catch (e) {
      showToast(t('systemTab.refreshFailed', { error: e instanceof Error ? e.message : String(e) }), 'error')
    }
  }

  const savePath = async () => {
    if (!editValue.trim()) return
    try {
      const result = await saveSettings({ model_cache_dir: editValue.trim() })
      if (result.success) {
        setEditingPath(null)
        void fetchPaths()
        showToast(t('systemTab.pathUpdated'), 'info')
      } else {
        showToast(t('systemTab.pathUpdateFailed', { error: result.error || '' }), 'error')
      }
    } catch (e) {
      showToast(t('systemTab.savePathFailed', { error: e instanceof Error ? e.message : String(e) }), 'error')
    }
  }

  useEffect(() => {
    void fetchEnv()
    void fetchModels()
    void fetchPaths()
  }, [fetchEnv, fetchModels, fetchPaths])

  if (loading && !env) {
    return (
      <div className="system-loading">
        {t('common.loading')}
      </div>
    )
  }

  if (!env) {
    return (
      <div className="system-error">
        {t('systemTab.loadingFailed')}
      </div>
    )
  }

  const coreLibs = env.capabilities.filter(c => c.category === 'core')
  const mdLibs = env.capabilities.filter(c => c.category === 'md')
  const dockingLibs = env.capabilities.filter(c => c.category === 'docking')
  const admetLibs = env.capabilities.filter(c => c.category === 'admet')

  const downloadedModels = models.filter(m => m.downloaded).length
  const totalDownloadedMB = models
    .filter(m => m.downloaded)
    .reduce((sum, m) => sum + m.actual_size_mb, 0)
  const totalEstimatedMB = models.reduce((sum, m) => sum + m.size_mb, 0)

  return (
    <div className="system-tab">
      <ModelServiceSection settings={settings} setSettings={setSettings} />

      <div>
        <div className="system-section-header">
          <SectionTitle>{t('settings.environment')}</SectionTitle>
          <Button
            variant="secondary"
            icon={<RefreshCwIcon size={14} />}
            onClick={handleRefreshModelEnv}
          >
            {t('systemTab.refreshModels')}
          </Button>
        </div>

        <div>
          <ResponsiveStatGrid style={{ marginBottom: '24px' }}>
            <StatCard label={t('systemTab.python')} value={env.python_version} />
            <StatCard
              label={t('systemTab.gpu')}
              value={env.gpu_name?.split(' ').slice(0, 2).join(' ') || t('systemTab.none')}
              subValue={env.cuda_version ? `CUDA ${env.cuda_version}` : undefined}
              variant={env.gpu_available ? 'success' : 'default'}
            />
            <StatCard
              label={t('systemTab.gpuMemory')}
              value={env.gpu_memory_mb ? `${Math.round(env.gpu_memory_mb / 1024)}GB` : t('systemTab.na')}
            />
            <StatCard
              label={t('systemTab.models')}
              value={`${downloadedModels}/${models.length}`}
              subValue={
                downloadedModels > 0
                  ? `${Math.round(totalDownloadedMB)} MB / ${totalEstimatedMB} MB`
                  : undefined
              }
              variant={downloadedModels === models.length && models.length > 0 ? 'success' : 'default'}
            />
          </ResponsiveStatGrid>

          <div className="system-library-list">
            <LibrarySection title={t('systemTab.coreLibraries')} libs={coreLibs} />
            {mdLibs.length > 0 && <LibrarySection title={t('systemTab.molecularDynamics')} libs={mdLibs} />}
            {dockingLibs.length > 0 && <LibrarySection title={t('systemTab.docking')} libs={dockingLibs} />}
            {admetLibs.length > 0 && <LibrarySection title={t('systemTab.admet')} libs={admetLibs} />}
          </div>

          <div className="system-block">
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

          <div className="system-block">
            <ModelsSection
              models={models}
              downloadedCount={downloadedModels}
              onDownload={handleDownloadModel}
              onDelete={handleDeleteModel}
            />
          </div>

          <div className="system-block">
            <DetectionCacheCard />
          </div>

          <div className="system-block">
            <SidecarCard />
          </div>
        </div>
      </div>
    </div>
  )
}
