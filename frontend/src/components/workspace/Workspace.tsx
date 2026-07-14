import { useCallback, useState } from 'react'
import { motion } from 'framer-motion'
import { fadeUp } from '@/hooks/useAnimations'
import { useAppContext } from '@/context/AppContext'
import { useDeleteDocument, useDocuments, useImportDocument } from '@/api/query/hooks'
import { showToast } from '@/hooks/useToast'
import { useTranslation } from 'react-i18next'
import { PdfIcon, PlusIcon, TrashIcon } from '@/components/icons'
import PageTitle from '@/components/ui/PageTitle'
import Skeleton from '@/components/ui/Skeleton'
import type { DocumentInfo } from '@/api/http/library'

export default function Workspace() {
  const { t } = useTranslation()
  const { libraryRoot, activeCollectionId, openTab } = useAppContext()
  const { data, isLoading, isError } = useDocuments(activeCollectionId ?? undefined)
  const importMutation = useImportDocument()
  const deleteMutation = useDeleteDocument()
  const documents = data?.documents ?? []
  const [isDraggingFile, setIsDraggingFile] = useState(false)

  const handleImportFile = useCallback(async (file: File) => {
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      showToast(t('library.importError', { error: 'PDF files only' }), 'error')
      return
    }
    try {
      await importMutation.mutateAsync({ file })
      showToast(t('library.importSuccess'), 'success')
    } catch (e) {
      showToast(t('library.importError', { error: e instanceof Error ? e.message : String(e) }), 'error')
    }
  }, [importMutation, t])

  const handleImport = useCallback(() => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.pdf'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      await handleImportFile(file)
    }
    input.click()
  }, [handleImportFile])

  const handleDrop = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDraggingFile(false)
    const file = event.dataTransfer.files[0]
    void handleImportFile(file)
  }, [handleImportFile])

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

  const handleDeleteDocument = useCallback(async (doc: DocumentInfo) => {
    if (!window.confirm(t('doc.deleteConfirm', { filename: doc.file_name }))) return

    try {
      await deleteMutation.mutateAsync(doc.doc_id)
      showToast(t('doc.deleteSuccess', { filename: doc.file_name }), 'success')
    } catch (e) {
      showToast(t('doc.deleteError', { error: e instanceof Error ? e.message : String(e) }), 'error')
    }
  }, [deleteMutation, t])

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
          <div className="workspace-skeleton" data-testid="workspace-skeleton" aria-busy="true">
            <div className="workspace-skeleton__title" />
            <div className="doc-grid">
              {Array.from({ length: 6 }, (_, index) => (
                <div key={index} className="workspace-skeleton__card">
                  <Skeleton variant="text" height={16} style={{ width: '72%' }} />
                  <Skeleton variant="text" height={12} style={{ width: '48%' }} />
                  <Skeleton variant="text" height={20} style={{ width: '28%', marginTop: 'auto' }} />
                </div>
              ))}
            </div>
          </div>
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
              <div
                className={`workspace-drop-zone${isDraggingFile ? ' is-dragging' : ''}`}
                onDragEnter={(event) => {
                  event.preventDefault()
                  setIsDraggingFile(true)
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setIsDraggingFile(false)}
                onDrop={handleDrop}
              >
                <PdfIcon size={28} aria-hidden="true" />
                <span>{t('library.emptyImportHint')}</span>
                <button className="workspace-import-btn" onClick={handleImport}>
                  <PlusIcon size={16} />
                  {t('library.importPdf')}
                </button>
              </div>
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
                <button
                  className="doc-card-delete"
                  type="button"
                  aria-label={t('doc.delete')}
                  title={t('doc.delete')}
                  disabled={deleteMutation.isPending}
                  onClick={(event) => {
                    event.stopPropagation()
                    void handleDeleteDocument(doc)
                  }}
                >
                  <TrashIcon size={16} />
                </button>
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
