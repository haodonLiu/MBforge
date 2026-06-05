import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  getFileTree,
  uploadFiles,
} from '../api/tauri-bridge'
import { PlusIcon } from './icons'
import { useAppContext } from '../context/AppContext'
import { showToast } from '../hooks/useToast'
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
  const { projectRoot } = useAppContext()
  const [tree, setTree] = useState<FileNode[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState('')

  const loadTree = useCallback(async () => {
    if (!projectRoot) return
    setIsLoading(true)
    setError('')
    try {
      const resp = await getFileTree(projectRoot)
      setTree(resp.tree)
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

  const handleImport = async () => {
    if (!projectRoot) return

    setIsUploading(true)
    try {
      await uploadFiles(projectRoot)
      loadTree()
    } catch (err) {
      showToast('导入失败: ' + (err instanceof Error ? err.message : String(err)), 'error')
    } finally {
      setIsUploading(false)
    }
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
        <Button
          variant="dashed"
          size="sm"
          onClick={handleImport}
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
