import { useState, useRef } from 'react'
import { createProject, openProject } from '../api/client'
import { FlaskIcon, UploadIcon, FolderIcon } from './icons'

interface Props {
  onProjectOpened?: (root: string) => void
}

export default function Welcome({ onProjectOpened }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [projectPath, setProjectPath] = useState('')
  const [projectName, setProjectName] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [isOpening, setIsOpening] = useState(false)

  const handleCreate = async () => {
    if (!projectPath.trim()) return
    setIsCreating(true)
    try {
      const resp = await createProject(projectPath.trim(), projectName.trim())
      if (resp.success && resp.project) {
        localStorage.setItem('mbforge_project_root', resp.project.root)
        onProjectOpened?.(resp.project.root)
      } else {
        alert(resp.error || '创建失败')
      }
    } catch (e) {
      alert(`创建失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setIsCreating(false)
    }
  }

  const handleOpen = async () => {
    if (!projectPath.trim()) return
    setIsOpening(true)
    try {
      const resp = await openProject(projectPath.trim())
      if (resp.success && resp.project) {
        localStorage.setItem('mbforge_project_root', resp.project.root)
        onProjectOpened?.(resp.project.root)
      } else {
        alert(resp.error || '打开失败，请确认路径有效')
      }
    } catch (e) {
      alert(`打开失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setIsOpening(false)
    }
  }

  const handleDirectorySelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    const firstFile = files[0]
    // In Tauri, the input returns absolute paths via webkitRelativePath or the file itself
    let selectedPath = ''

    // Try to get the full path from the file's webkitRelativePath
    const relativePath = firstFile.webkitRelativePath
    if (relativePath) {
      // webkitRelativePath is "FolderName/subfolder/file.txt"
      // We need the absolute path - extract from the file object
      // In a browser context we can't get the absolute path, but in Tauri we can
      // Try to use the path property (Tauri-specific)
      const anyFile = firstFile as any
      if (anyFile.path) {
        // Tauri file picker provides absolute path
        selectedPath = anyFile.path
        // Go up to the directory that was selected
        const parts = selectedPath.replace(/\\/g, '/').split('/')
        // Remove the filename to get the directory
        parts.pop()
        selectedPath = parts.join('/')
      } else {
        // Fallback: use relative path
        const rootFolder = relativePath.split('/')[0]
        selectedPath = `./${rootFolder}`
      }
    }

    if (selectedPath) {
      setProjectPath(selectedPath)
      // Auto-open: try create first, if it fails try open
      setIsCreating(true)
      try {
        const resp = await createProject(selectedPath, '')
        if (resp.success && resp.project) {
          localStorage.setItem('mbforge_project_root', resp.project.root)
          onProjectOpened?.(resp.project.root)
          return
        }
        // If create fails, try opening as existing project
        const openResp = await openProject(selectedPath)
        if (openResp.success && openResp.project) {
          localStorage.setItem('mbforge_project_root', openResp.project.root)
          onProjectOpened?.(openResp.project.root)
          return
        }
        // Both failed - let user see the path and try manually
        alert(openResp.error || '无法打开所选文件夹，请确认路径有效')
      } catch (e) {
        // Create failed, try open
        try {
          const openResp = await openProject(selectedPath)
          if (openResp.success && openResp.project) {
            localStorage.setItem('mbforge_project_root', openResp.project.root)
            onProjectOpened?.(openResp.project.root)
            return
          }
          alert(openResp.error || '无法打开所选文件夹')
        } catch (e2) {
          alert(`打开失败: ${e2 instanceof Error ? e2.message : String(e2)}`)
        }
      } finally {
        setIsCreating(false)
      }
    }
  }

  return (
    <div style={{
      flex: 1,
      padding: '32px',
      overflow: 'auto',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <div style={{
        maxWidth: '600px',
        margin: '60px auto',
        textAlign: 'center',
      }}>
        <div style={{
          width: '72px',
          height: '72px',
          background: 'var(--accent)',
          borderRadius: '18px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          margin: '0 auto 28px',
        }}>
          <FlaskIcon size={40} />
        </div>
        <h1 style={{
          fontSize: '32px',
          fontWeight: 700,
          letterSpacing: '-1px',
          marginBottom: '12px',
        }}>
          MBForge
        </h1>
        <p style={{
          fontSize: '16px',
          color: 'var(--text-secondary)',
          marginBottom: '36px',
        }}>
          Molecular Knowledge Base - 分子知识库
        </p>

        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          marginBottom: '24px',
        }}>
          <input
            type="text"
            value={projectPath}
            onChange={e => setProjectPath(e.target.value)}
            placeholder="项目路径 (如: ./my-project)"
            className="input"
          />
          <input
            type="text"
            value={projectName}
            onChange={e => setProjectName(e.target.value)}
            placeholder="项目名称 (可选)"
            className="input"
          />
        </div>

        <div style={{
          display: 'flex',
          gap: '12px',
          justifyContent: 'center',
        }}>
          <button
            className="btn btn-primary"
            onClick={handleCreate}
            disabled={isCreating || !projectPath.trim()}
          >
            {isCreating ? '创建中...' : '新建项目'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleOpen}
            disabled={isOpening || !projectPath.trim()}
          >
            {isOpening ? '打开中...' : '打开项目'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            // @ts-ignore - webkitdirectory is non-standard
            webkitdirectory=""
            multiple={false}
            style={{ display: 'none' }}
            onChange={handleDirectorySelect}
          />
          <button
            className="btn btn-secondary"
            onClick={() => fileInputRef.current?.click()}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <FolderIcon size={16} />
            浏览文件夹
          </button>
        </div>
      </div>

      <div style={{
        maxWidth: '600px',
        margin: '0 auto 40px',
        padding: '40px 32px',
        background: 'var(--bg-surface)',
        border: '2px dashed var(--border)',
        borderRadius: '16px',
        textAlign: 'center',
        cursor: 'pointer',
        transition: 'all 0.2s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--accent)'
        e.currentTarget.style.background = 'var(--accent-muted)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.background = 'var(--bg-surface)'
      }}
      onClick={() => alert('文件上传功能即将推出')}
      >
        <UploadIcon size={40} />
        <p style={{ marginTop: '16px', fontSize: '14px', color: 'var(--text-secondary)' }}>
          拖拽文件到此处，或<strong>点击上传</strong>
        </p>
        <p style={{
          fontSize: '12px',
          marginTop: '8px',
          color: 'var(--text-muted)',
        }}>
          支持 PDF, SDF, MOL, PDB, MD
        </p>
      </div>
    </div>
  )
}
