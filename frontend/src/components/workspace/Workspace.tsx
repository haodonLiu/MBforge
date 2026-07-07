import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { fadeUp } from '@/hooks/useAnimations'
import { useAppContext } from '@/context/AppContext'
import {
  listDocuments,
  importDocument,
  type DocumentInfo,
} from '@/api/http/library'
import { showToast } from '@/hooks/useToast'
import { useTranslation } from 'react-i18next'
import { PdfIcon, PlusIcon } from '@/components/icons'
import PageTitle from '@/components/ui/PageTitle'
export default function Workspace() {
  const { t } = useTranslation()
  const { libraryRoot, activeCollectionId, openTab } = useAppContext()
  const [documents, setDocuments] = useState<DocumentInfo[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!libraryRoot) return
    setLoading(true)
    void listDocuments(activeCollectionId ?? undefined)
      .then(r => setDocuments(r.documents))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [libraryRoot, activeCollectionId])

  const handleImport = async () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.pdf'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      try {
        const resp = await importDocument(file)
        if (resp.success) {
          showToast(t('library.importSuccess'), 'success')
          const r = await listDocuments(activeCollectionId ?? undefined)
          setDocuments(r.documents)
        } else {
          showToast(resp.error || t('library.importFailed'), 'error')
        }
      } catch (e) {
        showToast(t('library.importError', { error: e instanceof Error ? e.message : String(e) }), 'error')
      }
    }
    input.click()
  }

  const handleOpenDocument = (doc: DocumentInfo) => {
    openTab({
      type: 'pdf',
      title: doc.title,
      doc: { doc_id: doc.doc_id, path: doc.file_name },
      libraryRoot,
    })
  }

  const statusBadge = (status: string) => {
    const cls = status === 'ready' ? 'badge-ready' :
                status === 'indexing' ? 'badge-indexing' :
                status === 'error' ? 'badge-error' : 'badge-pending'
    return <span className={`doc-status-badge ${cls}`}>{status}</span>
  }

  return (
    <motion.div
      className="workspace-page"
      variants={fadeUp}
      initial="hidden"
      animate="visible"
    >
      <div className="workspace-header">
        <PageTitle>{t('library.documents')}</PageTitle>
        <button className="workspace-import-btn" onClick={handleImport}>
          <PlusIcon size={16} />
          {t('library.importPdf')}
        </button>
      </div>

      <div className="workspace-content">
        {loading ? (
          <div className="workspace-loading">Loading...</div>
        ) : documents.length === 0 ? (
          <div className="workspace-empty">
            <PdfIcon size={48} className="workspace-empty-icon" />
            <div className="workspace-empty-title">{t('library.noDocuments')}</div>
            <div className="workspace-empty-desc">
              {activeCollectionId
                ? t('library.emptyCollection')
                : t('library.emptyImportHint')}
            </div>
            {!activeCollectionId && (
              <button className="workspace-import-btn" onClick={handleImport}>
                <PlusIcon size={16} />
                {t('library.importPdf')}
              </button>
            )}
          </div>
        ) : (
          <div className="doc-grid">
            {documents.map(doc => (
              <div
                key={doc.doc_id}
                className="doc-card"
                onClick={() => handleOpenDocument(doc)}
              >
                <div className="doc-card-icon">
                  <PdfIcon size={32} />
                </div>
                <div className="doc-card-info">
                  <div className="doc-card-title" title={doc.title}>
                    {doc.title}
                  </div>
                  <div className="doc-card-meta">
                    <span>{doc.file_name}</span>
                    {doc.page_count > 0 && <span>{doc.page_count} pages</span>}
                  </div>
                </div>
                <div className="doc-card-status">
                  {statusBadge(doc.status)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  )
}
