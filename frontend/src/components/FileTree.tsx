import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { getFileTree, uploadFile } from '../api/client'
import { PlusIcon } from './icons'
import { getProjectRoot } from '../hooks/useProjectRoot'
import { default as BaseTreeNode } from '../components/ui/TreeNode'
import EmptyState from '../components/ui/EmptyState'
import Button from '../components/ui/Button'

interface FileNode {
  name: string
  path: string
  is_dir: boolean
  children: FileNode[]
}

interface Props {
  onFileClick?: (path: string) => void
}

function TreeNode({ node, depth, onFileClick }: { node: FileNode; depth: number; onFileClick?: (path: string) => void }) {
  const [expanded, setExpanded] = useState(depth < 1)

  if (node.is_dir) {
    return (
      <div>
        <BaseTreeNode
          node={{ ...node, children: [] }}
          depth={depth}
          expanded={expanded}
          onToggle={() => setExpanded(!expanded)}
        />
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: 'easeInOut' }}
              style={{ overflow: 'hidden' }}
            >
              {node.children.map(child => (
                <TreeNode key={child.path} node={child} depth={depth + 1} onFileClick={onFileClick} />
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    )
  }

  return (
    <BaseTreeNode
      node={node}
      depth={depth}
      onClick={() => onFileClick?.(node.path)}
    />
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
    return <EmptyState message={error} error />
  }

  if (isLoading) {
    return <EmptyState message="Loading..." />
  }

  if (tree.length === 0) {
    return <EmptyState message="No files found" />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ overflow: 'auto', flex: 1 }}>
        {tree.map(node => (
          <TreeNode key={node.path} node={node} depth={0} onFileClick={onFileClick} />
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
        <Button
          variant="dashed"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          icon={<PlusIcon size={14} />}
          style={{ width: '100%' }}
        >
          {isUploading ? '导入中...' : '导入文件'}
        </Button>
      </div>
    </div>
  )
}
