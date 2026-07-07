import { useState } from 'react'
import { ChevronRightIcon, ChevronDownIcon } from './icons/arrows'
import { FolderIcon } from './icons/nav'
import { PlusIcon } from './icons/actions'
import type { CollectionNode } from '../api/http/library'

interface Props {
  collections: CollectionNode[]
  activeId: string | null
  onSelect: (id: string | null) => void
  onCreateGroup: (name: string) => void
}

export default function GroupsPanel({ collections, activeId, onSelect, onCreateGroup }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleCreate = () => {
    if (newName.trim()) {
      onCreateGroup(newName.trim())
      setNewName('')
      setShowCreate(false)
    }
  }

  const renderNode = (node: CollectionNode, depth: number) => {
    const isExpanded = expanded.has(node.collection_id)
    const isActive = activeId === node.collection_id
    const hasChildren = node.children.length > 0

    return (
      <div key={node.collection_id}>
        <div
          className={`library-tree-node ${isActive ? 'library-tree-node--active' : ''}`}
          style={{ paddingLeft: `${12 + depth * 16}px` }}
          onClick={() => onSelect(node.collection_id)}
        >
          {hasChildren ? (
            <span
              className="library-tree-chevron"
              onClick={(e) => { e.stopPropagation(); toggleExpand(node.collection_id) }}
            >
              {isExpanded ? <ChevronDownIcon size={12} /> : <ChevronRightIcon size={12} />}
            </span>
          ) : (
            <span className="library-tree-chevron library-tree-chevron--spacer" />
          )}
          <FolderIcon size={14} />
          <span className="library-tree-label">{node.name}</span>
          <span className="library-tree-count">{node.doc_count}</span>
        </div>
        {hasChildren && isExpanded && (
          <div>{node.children.map(c => renderNode(c, depth + 1))}</div>
        )}
      </div>
    )
  }

  return (
    <div className="library-groups-panel">
      <div className="library-groups-header">
        <span className="library-groups-title">Groups</span>
        <button
          className="library-groups-add-btn"
          onClick={() => setShowCreate(!showCreate)}
          title="New Group"
        >
          <PlusIcon size={12} />
        </button>
      </div>

      {showCreate && (
        <div className="library-groups-create">
          <input
            type="text"
            className="library-groups-create-input"
            placeholder="Group name..."
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') { setShowCreate(false); setNewName('') } }}
            autoFocus
          />
          <button className="library-groups-create-btn" onClick={handleCreate}>
            Add
          </button>
        </div>
      )}

      <div className="library-tree">
        {collections.length === 0 ? (
          <div className="library-tree-empty">No groups yet</div>
        ) : (
          collections.map(c => renderNode(c, 0))
        )}
      </div>
    </div>
  )
}
