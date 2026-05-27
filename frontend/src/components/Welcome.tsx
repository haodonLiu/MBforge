import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { createProject, openProject } from '../api/client'
import { FlaskIcon, UploadIcon, FolderIcon } from './icons'

export default function Welcome() {
  const navigate = useNavigate()
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
        navigate('/project')
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
        navigate('/project')
      } else {
        alert(resp.error || '打开失败，请确认路径有效')
      }
    } catch (e) {
      alert(`打开失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setIsOpening(false)
    }
  }

  const handleDirectorySelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      const firstFile = files[0]
      // webkitRelativePath gives us "foldername/subfolder/file.txt"
      // We need just the root folder name
      const relativePath = firstFile.webkitRelativePath
      if (relativePath) {
        const rootFolder = relativePath.split('/')[0]
        // Use current directory as base, or just the folder name
        setProjectPath(`./${rootFolder}`)
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
