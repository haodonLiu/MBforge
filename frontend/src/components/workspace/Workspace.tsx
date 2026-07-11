import { useCallback } from 'react'
import { motion } from 'framer-motion'
import { fadeUp } from '@/hooks/useAnimations'
import { useAppContext } from '@/context/AppContext'
import { useDocuments, useImportDocument } from '@/api/query/hooks'
import { showToast } from '@/hooks/useToast'
import { useTranslation } from 'react-i18next'
import { PdfIcon, PlusIcon } from '@/components/icons'
import PageTitle from '@/components/ui/PageTitle'
import type { DocumentInfo } from '@/api/http/library'

export default function Workspace() {
  const { t } = useTranslation()
  const { libraryRoot, activeCollectionId, openTab } = useAppContext()
  const { data, isLoading, isError } = useDocuments(activeCollectionId ?? undefined)
  const importMutation = useImportDocument()
  const documents = data?.documents ?? []

  const handleImport = useCallback(() => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.pdf'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      try {
        await importMutation.mutateAsync({ file })
        showToast(t('library.importSuccess'), 'success')
      } catch (e) {
        showToast(t('library.importError', { error: e instanceof Error ? e.message : String(e) }), 'error')
      }
    }
    input.click()
  }, [importMutation, t])

  const handleOpenDocument = (doc: DocumentInfo) => {
    openTab({
      type: 'document',
      title: doc.title,
      doc: {
        doc_id: doc.doc_id,
        path: doc.file_name,
        doc_type: 'pdf',
        title: doc.title,
        indexed: false,
      },
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
        {isLoading ? (
          <div className="workspace-loading">Loading...</div>
        ) : isError ? (
          <div className="workspace-empty">
            <div className="workspace-empty-title">Error</div>
            <div className="workspace-empty-desc">Failed to load documents. Please try again.</div>
            <button className="workspace-import-btn" onClick={() => window.location.reload()}>
              Retry
            </button>
          </div>
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
