import { useState } from 'react'
import { createProject, openProject } from '../api/client'
import { FolderIcon, ArrowLeftIcon, MoleculeLogo, TrashIcon, XIcon } from './icons'

interface RecentProject {
  name: string
  path: string
}

const RECENT_KEY = 'mbforge_recent_projects'
const MAX_RECENT = 20

function loadRecent(): RecentProject[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
  } catch {
    return []
  }
}

function persistRecent(path: string, name: string) {
  const list = loadRecent()
  const filtered = list.filter(p => p.path !== path)
  const next = [
    { name: name || path.split(/[/\\]/).pop() || path, path },
    ...filtered,
  ].slice(0, MAX_RECENT)
  localStorage.setItem(RECENT_KEY, JSON.stringify(next))
}

function removeRecentFromStorage(path: string) {
  const list = loadRecent().filter(p => p.path !== path)
  localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  return list
}

/** 去掉路径首尾的引号 */
function sanitizePath(p: string): string {
  return p.replace(/^["']+|["']+$/g, '').trim()
}

interface Props {
  onProjectOpened?: (root: string) => void
}

type Page = 'home' | 'create' | 'open'

export default function Welcome({ onProjectOpened }: Props) {
  const [page, setPage] = useState<Page>('home')
  const [selectedDir, setSelectedDir] = useState('')
  const [projectName, setProjectName] = useState('')
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>(loadRecent)

  const handleProjectSuccess = (root: string, name: string) => {
    localStorage.setItem('mbforge_project_root', root)
    persistRecent(root, name)
    onProjectOpened?.(root)
  }

  const openByName = async (path: string) => {
    setLoading(true)
    try {
      const resp = await openProject(path)
      if (resp.success && resp.project) {
        handleProjectSuccess(resp.project.root, resp.project.name)
      } else {
        alert(resp.error || '打开失败，请确认路径有效')
      }
    } catch (e) {
      alert(`打开失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!selectedDir.trim() || !projectName.trim()) return
    const fullPath = `${selectedDir.trim()}/${projectName.trim()}`
    setLoading(true)
    try {
      const resp = await createProject(fullPath, projectName.trim())
      if (resp.success && resp.project) {
        handleProjectSuccess(resp.project.root, resp.project.name)
      } else {
        alert(resp.error || '创建失败')
      }
    } catch (e) {
      alert(`创建失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setLoading(false)
    }
  }

  const handleOpenDir = async () => {
    if (!selectedDir.trim()) return
    setLoading(true)
    try {
      const resp = await openProject(selectedDir.trim())
      if (resp.success && resp.project) {
        handleProjectSuccess(resp.project.root, resp.project.name)
      } else {
        alert(resp.error || '无法打开，请确认该目录是有效的 MBForge 项目')
      }
    } catch (e) {
      alert(`打开失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setLoading(false)
    }
  }

  const btnStyle = (primary = false): React.CSSProperties => ({
    padding: '10px 20px',
    borderRadius: '10px',
    cursor: loading ? 'not-allowed' : 'pointer',
    fontWeight: 500,
    fontSize: '14px',
    transition: 'all 0.15s',
    opacity: loading ? 0.6 : 1,
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
    background: primary ? 'var(--accent)' : 'var(--bg-surface)',
    color: primary ? '#fff' : 'var(--text-primary)',
    border: primary ? 'none' : '1px solid var(--border)',
  })

  // ---- 创建项目二级页 ----
  if (page === 'create') {
    return (
      <div style={{ flex: 1, padding: '32px', overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        <div style={{ maxWidth: '500px', margin: '60px auto 0', width: '100%' }}>
          <button
            onClick={() => { setPage('home'); setSelectedDir(''); setProjectName('') }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '24px', padding: 0 }}
          >
            <ArrowLeftIcon size={16} /> 返回
          </button>

          <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '24px' }}>新建项目</h2>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              项目目录
            </label>
            <input
              type="text"
              value={selectedDir}
              onChange={e => setSelectedDir(sanitizePath(e.target.value))}
              placeholder="输入父目录路径 (如: D:/research)"
              className="input"
              style={{ width: '100%', boxSizing: 'border-box' }}
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              项目名称
            </label>
            <input
              type="text"
              value={projectName}
              onChange={e => setProjectName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="如: aspirin-study"
              className="input"
              style={{ width: '100%', boxSizing: 'border-box' }}
              autoFocus
            />
          </div>

          {selectedDir && projectName && (
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px', padding: '10px 14px', background: 'var(--bg-surface)', borderRadius: '8px' }}>
              将创建: <strong>{selectedDir}/{projectName}</strong>
            </div>
          )}

          <button
            onClick={handleCreate}
            disabled={loading || !selectedDir.trim() || !projectName.trim()}
            style={btnStyle(true)}
          >
            {loading ? (
              <>
                <span style={{ display: 'inline-block', width: '14px', height: '14px', border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
                创建中...
              </>
            ) : '创建项目'}
          </button>
        </div>
      </div>
    )
  }

  // ---- 打开项目二级页 ----
  if (page === 'open') {
    return (
      <div style={{ flex: 1, padding: '32px', overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        <div style={{ maxWidth: '500px', margin: '60px auto 0', width: '100%' }}>
          <button
            onClick={() => { setPage('home'); setSelectedDir('') }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '24px', padding: 0 }}
          >
            <ArrowLeftIcon size={16} /> 返回
          </button>

          <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '24px' }}>打开已有项目</h2>

          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              项目路径
            </label>
            <input
              type="text"
              value={selectedDir}
              onChange={e => setSelectedDir(sanitizePath(e.target.value))}
              onKeyDown={e => e.key === 'Enter' && handleOpenDir()}
              placeholder="输入项目根目录路径"
              className="input"
              style={{ width: '100%', boxSizing: 'border-box' }}
              autoFocus
            />
          </div>

          <button
            onClick={handleOpenDir}
            disabled={loading || !selectedDir.trim()}
            style={btnStyle(true)}
          >
            {loading ? (
              <>
                <span style={{ display: 'inline-block', width: '14px', height: '14px', border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
                打开中...
              </>
            ) : '打开项目'}
          </button>
        </div>
      </div>
    )
  }

  // ---- 首页 ----
  return (
    <div style={{ flex: 1, padding: '32px', overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
      <div style={{ maxWidth: '600px', margin: '60px auto 0', textAlign: 'center', width: '100%' }}>
        {/* Logo */}
        <div style={{ margin: '0 auto 28px' }}>
          <MoleculeLogo size={72} />
        </div>
        <h1 style={{ fontSize: '32px', fontWeight: 700, letterSpacing: '-1px', marginBottom: '12px' }}>
          MBForge
        </h1>
        <p style={{ fontSize: '16px', color: 'var(--text-secondary)', marginBottom: '40px' }}>
          Molecular Knowledge Base - 分子知识库
        </p>

        {/* 操作按钮 */}
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', marginBottom: '48px' }}>
          <button onClick={() => setPage('create')} style={btnStyle(true)}>
            <FolderIcon size={16} /> 新建项目
          </button>
          <button onClick={() => setPage('open')} style={btnStyle()}>
            <FolderIcon size={16} /> 打开项目
          </button>
        </div>

        {/* 最近项目 */}
        {recentProjects.length > 0 && (
          <div style={{ textAlign: 'left' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <h2 style={{
                fontSize: '14px', fontWeight: 600, color: 'var(--text-secondary)',
                textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0,
              }}>
                最近项目
              </h2>
              <button
                onClick={() => { setEditing(!editing); setDeleting(null) }}
                title={editing ? '完成' : '编辑'}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer', padding: '4px',
                  color: editing ? 'var(--accent)' : 'var(--text-muted)', transition: 'color 0.15s',
                }}
              >
                <TrashIcon size={16} />
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {recentProjects.map((p) => (
                <div
                  key={p.path}
                  style={{
                    display: 'flex', alignItems: 'center',
                    padding: '12px 16px', background: 'var(--bg-surface)',
                    border: '1px solid var(--border)', borderRadius: '10px',
                    transition: 'all 0.15s', width: '100%', boxSizing: 'border-box',
                    borderColor: deleting === p.path ? '#e74c3c' : undefined,
                    opacity: deleting === p.path ? 0.5 : 1,
                  }}
                >
                  {editing && (
                    <button
                      onClick={() => {
                        setDeleting(p.path)
                        setTimeout(() => {
                          const updated = removeRecentFromStorage(p.path)
                          setRecentProjects(updated)
                          setDeleting(null)
                          if (updated.length === 0) setEditing(false)
                        }, 300)
                      }}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer', padding: '2px 8px 2px 0',
                        color: '#e74c3c', flexShrink: 0, transition: 'transform 0.15s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.2)'}
                      onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
                    >
                      <XIcon size={14} />
                    </button>
                  )}
                  <button
                    onClick={() => openByName(p.path)}
                    disabled={loading || deleting === p.path}
                    style={{
                      flex: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      background: 'none', border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
                      textAlign: 'left', padding: 0, opacity: loading ? 0.6 : 1,
                    }}
                  >
                    <span style={{ fontWeight: 500, fontSize: '14px', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginRight: '16px' }}>
                      {p.name}
                    </span>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 0 }}>
                      {p.path}
                    </span>
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
