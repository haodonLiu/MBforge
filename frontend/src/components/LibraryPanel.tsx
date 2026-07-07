import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { FileTextIcon, PlusIcon, SettingsIcon } from './icons'
import GroupsPanel from './GroupsPanel'
import { useAppContext } from '@/context/AppContext'
import {
  getLibraryStatus,
  importDocument,
  listCollections,
  createCollection,
  type CollectionNode,
} from '@/api/http/library'
import { showToast } from '@/hooks/useToast'

export default function LibraryPanel() {
  const { t } = useTranslation()
  const { libraryRoot, activeCollectionId, setActiveCollectionId } = useAppContext()
  const [status, setStatus] = useState<{ doc_count: number }>({ doc_count: 0 })
  const [collections, setCollections] = useState<CollectionNode[]>([])

  useEffect(() => {
    if (!libraryRoot) return
    void getLibraryStatus().then(s => setStatus({ doc_count: s.doc_count })).catch(() => {})
    void listCollections().then(r => setCollections(r.collections)).catch(() => {})
  }, [libraryRoot])

  const handleImport = async () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.pdf'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      try {
        const resp = await importDocument(file.name, file.name.replace(/\.pdf$/i, ''))
        if (resp.success) {
          showToast(t('library.importSuccess'), 'success')
          const s = await getLibraryStatus()
          setStatus({ doc_count: s.doc_count })
        } else {
          showToast(resp.error || t('library.importFailed'), 'error')
        }
      } catch (e) {
        showToast(t('library.importError', { error: e instanceof Error ? e.message : String(e) }), 'error')
      }
    }
    input.click()
  }

  const handleCreateGroup = async (name: string): Promise<string | undefined> => {
    try {
      const resp = await createCollection(name)
      if (resp.success && resp.collection) {
        const r = await listCollections()
        setCollections(r.collections)
        return resp.collection.collection_id
      } else {
        showToast(resp.error || 'Failed to create group', 'error')
        return undefined
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : String(e), 'error')
      return undefined
    }
  }

  return (
    <div className="library-panel">
      <div className="library-panel-header">
        <span className="library-panel-title">{t('library.title')}</span>
        <button className="library-panel-import-btn" onClick={handleImport} title={t('library.importPdf')}>
          <PlusIcon size={16} />
        </button>
      </div>

      <div className="library-panel-section">
        <div
          className={`library-panel-item ${activeCollectionId === null ? 'library-panel-item--active' : ''}`}
          onClick={() => setActiveCollectionId(null)}
        >
          <FileTextIcon size={14} />
          <span className="library-panel-item-label">All Documents</span>
          <span className="library-panel-item-count">{status.doc_count}</span>
        </div>
      </div>

      <GroupsPanel
        collections={collections}
        activeId={activeCollectionId}
        onSelect={setActiveCollectionId}
        onCreateGroup={handleCreateGroup}
      />

      <div className="library-panel-footer">
        <button className="library-panel-manage-btn">
          <SettingsIcon size={12} />
          Manage Groups
        </button>
      </div>
    </div>
  )
}
