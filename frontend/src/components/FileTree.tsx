import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { getFileTree as getFileTreeHttp, uploadFile } from '../api/client'
import {
  isTauriAvailable,
  getFileTree as getFileTreeTauri,
  uploadFiles as uploadFilesTauri,
} from '../api/tauri-bridge'
import { PlusIcon } from './icons'
import { useAppContext } from '../context/AppContext'
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
      let treeData: FileNode[] = []
      if (isTauriAvailable()) {
        const resp = await getFileTreeTauri(projectRoot)
        treeData = resp.tree
      } else {
        const resp = await getFileTreeHttp(projectRoot)
        if (resp.success && resp.tree) {
          treeData = resp.tree
        } else {
          setError(resp.error || 'Failed to load file tree')
        }
      }
      setTree(treeData)
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

    if (isTauriAvailable()) {
      setIsUploading(true)
      try {
        await uploadFilesTauri(projectRoot)
        loadTree()
      } catch (err) {
        console.error('Upload failed:', err)
      } finally {
        setIsUploading(false)
      }
      return
    }

    // Browser dev fallback: trigger hidden file input
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.pdf,.sdf,.mol,.pdb,.md,.txt,.csv'
    input.multiple = true
    input.onchange = async (e) => {
      const files = (e.target as HTMLInputElement).files
      if (!files || files.length === 0) return
      setIsUploading(true)
      for (let i = 0; i < files.length; i++) {
        try {
          await uploadFile(projectRoot, files[i])
        } catch (err) {
          console.error('Upload failed:', err)
        }
      }
      setIsUploading(false)
      loadTree()
    }
    input.click()
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
