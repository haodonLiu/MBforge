import { useState, useEffect } from 'react'
import { RefreshCwIcon, CheckIcon, XIcon, DownloadIcon, TrashIcon, EditIcon, FolderIcon } from './icons'
import { PageContainer, PageTitle } from './ui'

interface EnvironmentCheckResult {
  python_version: string
  gpu_available: boolean
  gpu_name: string | null
  gpu_memory_mb: number | null
  cuda_version: string | null
  capabilities: CapabilityStatus[]
}

interface CapabilityStatus {
  name: string
  available: boolean
  version: string | null
  description: string
  category: string
}

interface ModelLocation {
  source: string
  path: string
  size_mb: number
}

interface ModelInfo {
  id: string
  name: string
  type: string
  description: string
  downloaded: boolean
  downloading: boolean
  size_mb: number
  actual_size_mb: number
  license: string
  location: {
    found: boolean
    locations: ModelLocation[]
    primary: string | null
  }
}

interface ModelPaths {
  mbforge: { path: string; exists: boolean; size_mb: number }
  huggingface: { path: string; env_var: string; exists: boolean; size_mb: number }
  modelscope: { path: string; env_var: string; exists: boolean; size_mb: number }
}

// 库信息
const LIBRARY_INFO: Record<string, { name: string; hint?: string }> = {
  rdkit:    { name: 'RDKit', hint: '分子信息学' },
  numpy:    { name: 'NumPy', hint: '数值计算' },
  scipy:    { name: 'SciPy', hint: '科学计算' },
  pandas:   { name: 'Pandas', hint: '数据分析' },
  openmm:   { name: 'OpenMM', hint: '分子动力学' },
  vina:     { name: 'AutoDock Vina', hint: '分子对接' },
  deepchem: { name: 'DeepChem', hint: 'ADMET 预测' },
  torch:    { name: 'PyTorch', hint: '深度学习' },
}

// 统计卡片组件
function StatCard({ label, value, subValue, variant = 'default' }: {
  label: string
  value: string | number
  subValue?: string
  variant?: 'default' | 'success' | 'danger'
}) {
  const bgColors = {
    default: 'var(--bg-surface)',
    success: 'rgba(22, 163, 74, 0.08)',
    danger: 'rgba(220, 38, 38, 0.08)',
  }
  const textColors = {
    default: 'var(--text-primary)',
    success: 'var(--success)',
    danger: 'var(--danger)',
  }
  
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '4px',
      padding: '16px',
      background: bgColors[variant],
      borderRadius: '10px',
      border: '1px solid var(--border)',
    }}>
      <div style={{ 
        fontSize: '11px', 
        color: 'var(--text-muted)', 
        textTransform: 'uppercase', 
        letterSpacing: '0.5px' 
      }}>
        {label}
      </div>
      <div style={{ 
        fontSize: '20px', 
        fontWeight: 700, 
        color: textColors[variant] 
      }}>
        {value}
      </div>
      {subValue && (
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          {subValue}
        </div>
      )}
    </div>
  )
}

// 库行组件
function LibRow({ lib }: { lib: CapabilityStatus }) {
  const info = LIBRARY_INFO[lib.name] || { name: lib.name }
  
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '12px 16px',
      background: 'var(--bg-base)',
      borderRadius: '8px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{
          width: '24px',
          height: '24px',
          borderRadius: '50%',
          background: lib.available ? 'var(--success)' : 'var(--danger)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          flexShrink: 0,
        }}>
          {lib.available ? <CheckIcon size={12} /> : <XIcon size={12} />}
        </div>
        <div>
          <div style={{ fontSize: '14px', fontWeight: 500 }}>
            {info.name}
          </div>
          {info.hint && (
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              {info.hint}
            </div>
          )}
        </div>
      </div>
      <div style={{
        fontSize: '13px',
        color: lib.available ? 'var(--success)' : 'var(--text-muted)',
      }}>
        {lib.available ? lib.version || 'Installed' : 'Not installed'}
      </div>
    </div>
  )
}

// 库分类区块
function LibrarySection({ title, libs }: { title: string; libs: CapabilityStatus[] }) {
  return (
    <div style={{
      padding: '16px 20px',
      background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderRadius: '12px',
    }}>
      <div style={{ 
        fontSize: '12px', 
        fontWeight: 600, 
        color: 'var(--text-muted)', 
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        marginBottom: '12px',
      }}>
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {libs.map(lib => (
          <LibRow key={lib.name} lib={lib} />
        ))}
      </div>
    </div>
  )
}

// 路径卡片组件
function PathCard({ 
  title, 
  path, 
  exists, 
  size_mb, 
  envVar,
  isEditing,
  editValue,
  onEdit,
  onSave,
  onCancel,
  onChange,
}: { 
  title: string
  path: string
  exists: boolean
  size_mb: number
  envVar?: string
  isEditing?: boolean
  editValue?: string
  onEdit?: () => void
  onSave?: () => void
  onCancel?: () => void
  onChange?: (value: string) => void
}) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '14px 16px',
      background: 'var(--bg-base)',
      borderRadius: '8px',
      border: '1px solid var(--border)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: 0 }}>
        <div style={{
          width: '24px',
          height: '24px',
          borderRadius: '6px',
          background: exists ? 'var(--success)' : 'var(--bg-surface)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: exists ? 'white' : 'var(--text-muted)',
          flexShrink: 0,
        }}>
          <FolderIcon size={14} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '13px', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '8px' }}>
            {title}
            {envVar && (
              <span style={{
                fontSize: '10px',
                padding: '2px 6px',
                background: 'var(--bg-surface)',
                borderRadius: '4px',
                color: 'var(--text-muted)',
              }}>
                {envVar}
              </span>
            )}
          </div>
          {isEditing ? (
            <input
              type="text"
              value={editValue}
              onChange={(e) => onChange?.(e.target.value)}
              style={{
                width: '100%',
                marginTop: '6px',
                padding: '6px 10px',
                background: 'var(--bg-surface)',
                border: '1px solid var(--accent)',
                borderRadius: '6px',
                fontSize: '12px',
                color: 'var(--text-primary)',
              }}
            />
          ) : (
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px', wordBreak: 'break-all' }}>
              {path}
            </div>
          )}
        </div>
      </div>
      
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginLeft: '16px' }}>
        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          {exists ? `${size_mb} MB` : 'Not found'}
        </span>
        
        {isEditing ? (
          <div style={{ display: 'flex', gap: '4px' }}>
            <button
              onClick={onSave}
              style={{
                padding: '4px 10px',
                background: 'var(--success)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '11px',
                color: 'white',
              }}
            >
              Save
            </button>
            <button
              onClick={onCancel}
              style={{
                padding: '4px 10px',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '11px',
                color: 'var(--text-secondary)',
              }}
            >
              Cancel
            </button>
          </div>
        ) : onEdit ? (
          <button
            onClick={onEdit}
            style={{
              padding: '4px 10px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '11px',
              color: 'var(--text-secondary)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <EditIcon size={12} />
            Edit
          </button>
        ) : null}
      </div>
    </div>
  )
}

// 模型卡片组件
function ModelCard({ model, onDownload, onDelete }: { 
  model: ModelInfo
  onDownload: (id: string) => void
  onDelete: (id: string) => void
}) {
  const typeColors: Record<string, { bg: string; text: string }> = {
    embedding: { bg: 'rgba(59, 130, 246, 0.1)', text: '#3b82f6' },
    reranker: { bg: 'rgba(168, 85, 247, 0.1)', text: '#a855f7' },
    detection: { bg: 'rgba(245, 158, 11, 0.1)', text: '#f59e0b' },
  }
  const typeColor = typeColors[model.type] || typeColors.detection
  
  // 显示大小
  const displaySize = model.downloaded ? model.actual_size_mb : model.size_mb
  const sizeLabel = model.downloaded 
    ? `${displaySize} MB` 
    : `~${displaySize} MB`
  
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '14px 16px',
      background: 'var(--bg-base)',
      borderRadius: '8px',
      border: model.downloaded ? '1px solid var(--success)' : '1px solid var(--border)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: 0 }}>
        <div style={{
          width: '24px',
          height: '24px',
          borderRadius: '50%',
          background: model.downloaded ? 'var(--success)' : 'var(--text-muted)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          flexShrink: 0,
        }}>
          {model.downloaded ? <CheckIcon size={12} /> : null}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '14px', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '8px' }}>
            {model.name}
            <span style={{
              fontSize: '10px',
              padding: '2px 6px',
              background: typeColor.bg,
              color: typeColor.text,
              borderRadius: '4px',
            }}>
              {model.type}
            </span>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
            {model.description}
          </div>
          {model.downloaded && (
            <div style={{ fontSize: '11px', color: 'var(--success)', marginTop: '4px' }}>
              Downloaded: {model.actual_size_mb} MB
              {model.location.primary && ` from ${model.location.primary}`}
            </div>
          )}
        </div>
      </div>
      
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginLeft: '16px' }}>
        <span style={{ 
          fontSize: '12px', 
          color: model.downloaded ? 'var(--success)' : 'var(--text-muted)', 
          whiteSpace: 'nowrap',
          fontWeight: model.downloaded ? 500 : 400,
        }}>
          {sizeLabel}
        </span>
        
        {model.downloading ? (
          <div style={{
            padding: '6px 12px',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            fontSize: '12px',
            color: 'var(--text-secondary)',
          }}>
            Downloading...
          </div>
        ) : model.downloaded ? (
          <button
            onClick={() => onDelete(model.id)}
            style={{
              padding: '6px 12px',
              background: 'rgba(220, 38, 38, 0.08)',
              border: '1px solid rgba(220, 38, 38, 0.2)',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '12px',
              color: 'var(--danger)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <TrashIcon size={12} />
            Delete
          </button>
        ) : (
          <button
            onClick={() => onDownload(model.id)}
            style={{
              padding: '6px 12px',
              background: 'var(--accent)',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '12px',
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <DownloadIcon size={12} />
            Download
          </button>
        )}
      </div>
    </div>
  )
}

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
        if (data.success) {
          setModels(data.models)
        }
      })
      .catch(console.error)
  }

  const fetchPaths = () => {
    fetch('/api/v1/download/model-paths')
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          setPaths(data.paths)
        }
      })
      .catch(console.error)
  }

  const downloadModel = async (modelId: string) => {
    try {
      const response = await fetch(`/api/v1/download/${modelId}`, { 
        method: 'POST'
      })
      
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
      const response = await fetch(`/api/v1/download/delete/${modelId}`, { method: 'DELETE' })
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
    return (
      <PageContainer>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '80px',
          color: 'var(--text-secondary)',
        }}>
          <RefreshCwIcon size={20} style={{ marginRight: '12px', animation: 'spin 1s linear infinite' }} />
          Checking environment...
        </div>
      </PageContainer>
    )
  }

  if (!env) {
    return (
      <PageContainer>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '80px',
          color: 'var(--danger)',
        }}>
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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <PageTitle>Environment</PageTitle>
        <button
          onClick={() => { fetchEnv(); fetchModels(); fetchPaths() }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 16px',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            cursor: 'pointer',
            fontSize: '13px',
            color: 'var(--text-secondary)',
          }}
        >
          <RefreshCwIcon size={14} />
          Refresh
        </button>
      </div>

      {/* 统计卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '24px' }}>
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
          subValue={downloadedModels > 0 ? `${Math.round(totalDownloadedMB)} MB / ${totalEstimatedMB} MB` : undefined}
          variant={downloadedModels === models.length && models.length > 0 ? 'success' : 'default'}
        />
      </div>

      {/* 库列表 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '24px' }}>
        <LibrarySection title="Core Libraries" libs={coreLibs} />
        {mdLibs.length > 0 && (
          <LibrarySection title="Molecular Dynamics" libs={mdLibs} />
        )}
        {dockingLibs.length > 0 && (
          <LibrarySection title="Docking" libs={dockingLibs} />
        )}
        {admetLibs.length > 0 && (
          <LibrarySection title="ADMET" libs={admetLibs} />
        )}
      </div>

      {/* 模型存储路径 */}
      <div style={{
        padding: '16px 20px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        marginBottom: '24px',
      }}>
        <div style={{ 
          fontSize: '12px', 
          fontWeight: 600, 
          color: 'var(--text-muted)', 
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          marginBottom: '16px',
        }}>
          Model Cache Paths
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {paths && (
            <>
              <PathCard
                title="MBForge"
                path={paths.mbforge.path}
                exists={paths.mbforge.exists}
                size_mb={paths.mbforge.size_mb}
                isEditing={editingPath === 'mbforge'}
                editValue={editValue}
                onEdit={() => {
                  setEditingPath('mbforge')
                  setEditValue(paths.mbforge.path)
                }}
                onSave={savePath}
                onCancel={() => setEditingPath(null)}
                onChange={setEditValue}
              />
              <PathCard
                title="HuggingFace"
                path={paths.huggingface.path}
                exists={paths.huggingface.exists}
                size_mb={paths.huggingface.size_mb}
                envVar={paths.huggingface.env_var}
              />
              <PathCard
                title="ModelScope"
                path={paths.modelscope.path}
                exists={paths.modelscope.exists}
                size_mb={paths.modelscope.size_mb}
                envVar={paths.modelscope.env_var}
              />
            </>
          )}
        </div>
      </div>

      {/* AI Models */}
      <div style={{
        padding: '16px 20px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
      }}>
        <div style={{ 
          fontSize: '12px', 
          fontWeight: 600, 
          color: 'var(--text-muted)', 
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          marginBottom: '16px',
        }}>
          AI Models ({downloadedModels}/{models.length} downloaded)
        </div>
        
        {models.length === 0 ? (
          <div style={{
            padding: '24px',
            textAlign: 'center',
            color: 'var(--text-muted)',
            fontSize: '13px',
          }}>
            Loading models...
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {models.map(model => (
              <ModelCard 
                key={model.id} 
                model={model} 
                onDownload={downloadModel}
                onDelete={deleteModel}
              />
            ))}
          </div>
        )}
      </div>
    </PageContainer>
  )
}
