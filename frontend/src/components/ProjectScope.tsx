import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  listProjectDocuments,
  uploadFiles,
  enqueueUnresolvedDocuments,
  type DocumentEntry,
} from '../api/http'
import { useAppContext } from '../context/AppContext'
import { showToast } from '../hooks/useToast'
import { FileTextIcon } from './icons/nav'
import { CheckIcon, PlusIcon } from './icons/actions'
import EmptyState from './ui/EmptyState'
import Button from './ui/Button'
import ScrollColumn from './ui/ScrollColumn'

interface Props {
  onFileClick?: (path: string) => void
}

function basename(p: string): string {
  return p.split(/[\\/]/).pop() || p
}

export default function ProjectScope({ onFileClick }: Props) {
  const { projectRoot } = useAppContext()
  const { t } = useTranslation()
  const [docs, setDocs] = useState<DocumentEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState('')

  const loadDocs = useCallback(async () => {
    if (!projectRoot) return
    setIsLoading(true)
    setError('')
    try {
      const resp = await listProjectDocuments(projectRoot)
      const filtered = resp.documents.filter(
        (d) => d.doc_type === 'pdf' && d.index_status === 'done',
      )
      setDocs(filtered)
    } catch (e) {
      console.error('[ProjectScope] load failed:', e)
      setError(t('projectScope.loadFailed') || '加载项目文献失败')
    } finally {
      setIsLoading(false)
    }
  }, [projectRoot, t])

  useEffect(() => {
    void loadDocs()
  }, [loadDocs])

  const handleImport = async () => {
    if (!projectRoot) return
    setIsUploading(true)
    try {
      await uploadFiles(projectRoot)
      await enqueueUnresolvedDocuments(projectRoot)
      await loadDocs()
    } catch (err) {
      showToast(
        `${t('projectScope.importFailed') || '导入失败'}: ${err instanceof Error ? err.message : String(err)}`,
        'error',
      )
    } finally {
      setIsUploading(false)
    }
  }

  if (error) {
    return <EmptyState message={error} error />
  }

  if (isLoading && docs.length === 0) {
    return <EmptyState message={t('common.loading') || '加载中…'} />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <ScrollColumn>
        {docs.length === 0 ? (
          <EmptyState message={t('projectScope.empty') || '暂无已解析的 PDF'} />
        ) : (
          <ul className="project-scope-list">
            {docs.map((doc) => (
              <li key={doc.doc_id}>
                <button
                  className="project-scope-item"
                  type="button"
                  onClick={() => onFileClick?.(doc.path)}
                  title={doc.title || basename(doc.path)}
                >
                  <span className="project-scope-icon">
                    <FileTextIcon size={16} />
                  </span>
                  <span className="project-scope-title">{doc.title || basename(doc.path)}</span>
                  <span className="project-scope-status">
                    <CheckIcon size={12} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </ScrollColumn>
      <div
        style={{
          padding: '10px 12px',
          borderTop: '1px solid var(--border)',
        }}
      >
        <Button
          variant="dashed"
          size="sm"
          onClick={handleImport}
          disabled={isUploading}
          icon={<PlusIcon size={14} />}
          style={{ width: '100%' }}
        >
          {isUploading ? t('projectScope.importing') || '导入中…' : t('projectScope.import') || '导入 PDF'}
        </Button>
      </div>
    </div>
  )
}
