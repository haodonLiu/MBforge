import { useState, useEffect, useCallback, useRef } from 'react'
import { getFileTree, uploadFile } from '../api/client'
import { FolderIcon, FileTextIcon, ChevronRightIcon, PlusIcon } from './icons'
import { getProjectRoot } from '../hooks/useProjectRoot'

interface FileNode {
  name: string
  path: string
  is_dir: boolean
  children: FileNode[]
}

interface Props {
  onFileClick?: (path: string) => void
}

function TreeItem({ node, depth, onFileClick }: { node: FileNode; depth: number; onFileClick?: (path: string) => void }) {
  const [expanded, setExpanded] = useState(depth < 1)

  if (node.is_dir) {
    return (
      <div>
        <div
          onClick={() => setExpanded(!expanded)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '4px 8px',
            paddingLeft: `${8 + depth * 16}px`,
            cursor: 'pointer',
            fontSize: '13px',
            color: 'var(--text-primary)',
            borderRadius: '4px',
            transition: 'background 0.1s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
        >
          <span style={{
            display: 'inline-flex',
            transition: 'transform 0.15s',
            transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
          }}>
            <ChevronRightIcon size={12} />
          </span>
          <FolderIcon size={14} />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {node.name}
          </span>
        </div>
        {expanded && node.children.map(child => (
          <TreeItem key={child.path} node={child} depth={depth + 1} onFileClick={onFileClick} />
        ))}
      </div>
    )
  }

  return (
    <div
      onClick={() => onFileClick?.(node.path)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        padding: '4px 8px',
        paddingLeft: `${8 + depth * 16}px`,
        cursor: 'pointer',
        fontSize: '13px',
        color: 'var(--text-secondary)',
        borderRadius: '4px',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background = 'var(--bg-hover)'
        e.currentTarget.style.color = 'var(--text-primary)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = 'transparent'
        e.currentTarget.style.color = 'var(--text-secondary)'
      }}
    >
      <FileTextIcon size={14} />
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {node.name}
      </span>
    </div>
  )
}

export default function FileTree({ onFileClick }: Props) {
  const [tree, setTree] = useState<FileNode[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadTree = useCallback(async () => {
    const root = getProjectRoot()
    if (!root) return
    setIsLoading(true)
    setError('')
    try {
      const resp = await getFileTree(root)
      if (resp.success && resp.tree) {
        setTree(resp.tree)
      } else {
        setError(resp.error || 'Failed to load file tree')
      }
    } catch (e) {
      console.error(e)
      setError('Failed to load file tree')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadTree()
  }, [loadTree])

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    const root = getProjectRoot()
    if (!root) return

    setIsUploading(true)
    for (let i = 0; i < files.length; i++) {
      try {
        await uploadFile(root, files[i])
      } catch (err) {
        console.error('Upload failed:', err)
      }
    }
    setIsUploading(false)
    e.target.value = ''
    loadTree()
  }

  if (error) {
    return (
      <div style={{
        padding: '16px 12px',
        fontSize: '12px',
        color: 'var(--text-muted)',
        textAlign: 'center',
      }}>
        {error}
      </div>
    )
  }

  if (isLoading) {
    return (
      <div style={{
        padding: '16px 12px',
        fontSize: '12px',
        color: 'var(--text-muted)',
        textAlign: 'center',
      }}>
        Loading...
      </div>
    )
  }

  if (tree.length === 0) {
    return (
      <div style={{
        padding: '16px 12px',
        fontSize: '12px',
        color: 'var(--text-muted)',
        textAlign: 'center',
      }}>
        No files found
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ overflow: 'auto', flex: 1 }}>
        {tree.map(node => (
          <TreeItem key={node.path} node={node} depth={0} onFileClick={onFileClick} />
        ))}
      </div>
      <div style={{
        padding: '10px 12px',
        borderTop: '1px solid var(--border)',
      }}>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.sdf,.mol,.pdb,.md,.txt,.csv"
          multiple
          style={{ display: 'none' }}
          onChange={handleImport}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          style={{
            width: '100%',
            padding: '8px 0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            background: 'none',
            border: '1px dashed var(--border)',
            borderRadius: '8px',
            color: isUploading ? 'var(--text-muted)' : 'var(--text-secondary)',
            fontSize: '12px',
            cursor: isUploading ? 'not-allowed' : 'pointer',
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => {
            if (!isUploading) {
              e.currentTarget.style.borderColor = 'var(--accent)'
              e.currentTarget.style.color = 'var(--accent)'
            }
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor = 'var(--border)'
            e.currentTarget.style.color = 'var(--text-secondary)'
          }}
        >
          <PlusIcon size={14} />
          {isUploading ? '导入中...' : '导入文件'}
        </button>
      </div>
    </div>
  )
}
