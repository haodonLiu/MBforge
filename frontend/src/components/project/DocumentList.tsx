import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { motion } from 'framer-motion'

import BodyText from '../ui/BodyText'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import Skeleton from '../ui/Skeleton'
import EmptyState from '../ui/EmptyState'
import { FileTextIcon } from '../icons'
import { inspectPdf, confirmOcr } from '../../api/tauri/pdf'
import { ingestEnqueue, trackSelfTriggeredDoc } from '../../api/tauri/ingest_queue'
import { showToast } from '../../hooks/useToast'
import type { DocumentEntry } from '../../types'

interface DocumentListProps {
  docs: DocumentEntry[]
  isLoading: boolean
  projectRoot: string
  onOpenFile: (doc: DocumentEntry) => void
  onRefreshDocs?: () => void
}

export default function DocumentList({ docs, isLoading, projectRoot, onOpenFile, onRefreshDocs }: DocumentListProps) {
  const { t } = useTranslation()
  const inspectedRef = useRef<Set<string>>(new Set())
  const [inspectingIds, setInspectingIds] = useState<Set<string>>(new Set())
  const [confirmingIds, setConfirmingIds] = useState<Set<string>>(new Set())
  const [enqueueingIds, setEnqueueingIds] = useState<Set<string>>(new Set())
  const [justEnqueuedIds, setJustEnqueuedIds] = useState<Set<string>>(new Set())

  // 对未检测的 PDF 自动运行 Inspector（仅一次）
  useEffect(() => {
    if (!projectRoot || isLoading) return
    for (const doc of docs) {
      if (doc.doc_type !== 'pdf') continue
      const status = doc.inspector_status || 'pending'
      if (status === 'pending' && !inspectedRef.current.has(doc.doc_id)) {
        inspectedRef.current.add(doc.doc_id)
        setInspectingIds(prev => new Set(prev).add(doc.doc_id))
        inspectPdf(projectRoot, doc.doc_id)
          .then(() => {
            onRefreshDocs?.()
          })
          .catch((e: unknown) => {
            console.warn('[DocumentList] inspect failed:', e)
          })
          .finally(() => {
            setInspectingIds(prev => {
              const next = new Set(prev)
              next.delete(doc.doc_id)
              return next
            })
          })
      }
    }
  }, [docs, isLoading, projectRoot, onRefreshDocs])

  const handleConfirmOcr = async (doc: DocumentEntry, confirm: boolean) => {
    if (!projectRoot) return
    setConfirmingIds(prev => new Set(prev).add(doc.doc_id))
    try {
      await confirmOcr(projectRoot, doc.doc_id, confirm)
      if (confirm) {
        setJustEnqueuedIds(prev => new Set(prev).add(doc.doc_id))
      }
      showToast(confirm ? t('doc.ocrConfirmed') : t('doc.ocrSkipped'), 'success')
      onRefreshDocs?.()
    } catch (e) {
      console.error('[DocumentList] confirm OCR failed:', e)
      showToast(t('doc.ocrConfirmFailed', { error: String(e) }), 'error')
    } finally {
      setConfirmingIds(prev => {
        const next = new Set(prev)
        next.delete(doc.doc_id)
        return next
      })
    }
  }

  const handleEnqueue = async (doc: DocumentEntry) => {
    if (!projectRoot) return
    const filePath = doc.source_path || `${projectRoot}/projects/${doc.doc_id}/source.pdf`
    setEnqueueingIds(prev => new Set(prev).add(doc.doc_id))
    try {
      await ingestEnqueue(projectRoot, filePath, doc.doc_id)
      trackSelfTriggeredDoc(doc.doc_id)
      setJustEnqueuedIds(prev => new Set(prev).add(doc.doc_id))
      showToast(t('project.processNow') + ': ' + (doc.title || doc.doc_id), 'success')
      onRefreshDocs?.()
    } catch (e) {
      console.error('[DocumentList] enqueue failed:', e)
      showToast(t('doc.enqueueFailed', { error: String(e) }), 'error')
    } finally {
      setEnqueueingIds(prev => {
        const next = new Set(prev)
        next.delete(doc.doc_id)
        return next
      })
    }
  }

  if (isLoading) {
    return (
      <div className="project-doc-list-loading">
        <Skeleton variant="row" count={5} height={48} />
      </div>
    )
  }

  if (docs.length === 0) {
    return (
      <EmptyState
        message={projectRoot ? t('doc.emptyWithProject') : t('project.noProject')}
      />
    )
  }

  return (
    <div className="project-docs-list">
      {docs.map((doc, index) => {
        const isInspecting = inspectingIds.has(doc.doc_id)
        const isConfirming = confirmingIds.has(doc.doc_id)
        const justEnqueued = justEnqueuedIds.has(doc.doc_id)

        const inspectorStatus = doc.inspector_status || 'pending'
        const inspectorBadge =
          doc.doc_type !== 'pdf'
            ? null
            : inspectorStatus === 'text_based'
              ? <Badge variant="success">{t('doc.typeText')}</Badge>
              : inspectorStatus === 'scanned'
                ? <Badge variant="warning">{t('doc.typeScanned')}</Badge>
                : inspectorStatus === 'mixed'
                  ? <Badge variant="warning">{t('doc.typeMixed')}</Badge>
                  : inspectorStatus === 'image_based'
                    ? <Badge variant="neutral">{t('doc.typeImage')}</Badge>
                    : inspectorStatus === 'error'
                      ? <Badge variant="danger">{t('doc.detectFailed')}</Badge>
                      : <Badge variant="neutral">{t('doc.pendingDetect')}</Badge>

        const textStatus = doc.text_status || 'pending'
        const textBadge =
          doc.doc_type !== 'pdf'
            ? null
            : textStatus === 'done'
              ? <Badge variant="success">{t('doc.textExtracted')}</Badge>
              : textStatus === 'error'
                ? <Badge variant="danger">{t('doc.extractFailed')}</Badge>
                : null

        const ocrStatus = doc.ocr_status || 'not_processed'
        const ocrBadge =
          doc.doc_type !== 'pdf'
            ? null
            : ocrStatus === 'done' || ocrStatus === 'completed'
              ? <Badge variant="success">{t('doc.ocrDone')}</Badge>
              : ocrStatus === 'processing'
                ? <Badge variant="warning">{t('doc.ocrProcessing')}</Badge>
              : ocrStatus === 'pending'
                ? <Badge variant="warning">{t('doc.pendingOcr')}</Badge>
              : ocrStatus === 'pending_confirmation'
                ? <Badge variant="warning">{t('doc.pendingOcrConfirm')}</Badge>
              : ocrStatus === 'skipped'
                ? null
              : ocrStatus === 'error'
                ? <Badge variant="danger">{t('doc.ocrFailed')}</Badge>
                : null

        const moldetStatus = doc.moldet_status || 'not_processed'
        const moldetBadge =
          doc.doc_type !== 'pdf'
            ? null
            : moldetStatus === 'has_molecule'
              ? <Badge variant="success">{t('doc.hasMolecule')}</Badge>
              : moldetStatus === 'no_molecule'
                ? null
                : moldetStatus === 'error'
                  ? <Badge variant="danger">检测失败</Badge>
                  : null

        const indexStatus = doc.index_status || 'pending'
        const indexBadge =
          doc.doc_type !== 'pdf'
            ? null
            : indexStatus === 'done'
              ? <Badge variant="success">{t('doc.indexedInKb')}</Badge>
              : indexStatus === 'error'
                ? <Badge variant="danger">{t('doc.indexFailed')}</Badge>
                : null

        const moldetHint =
          doc.doc_type === 'pdf' && doc.moldet_pages && doc.moldet_pages.length > 0
            ? `${t('doc.moleculePages', { pages: doc.moldet_pages.join(', ') })}`
            : undefined

        const needsOcrConfirm = doc.doc_type === 'pdf' && ocrStatus === 'pending_confirmation'
        const isEnqueueing = enqueueingIds.has(doc.doc_id)

        // 判断文件是否正在处理中（任何阶段）
        const isActivelyProcessing =
          doc.doc_type === 'pdf' && (
            justEnqueued ||
            isInspecting ||
            isConfirming ||
            isEnqueueing ||
            ocrStatus === 'processing' ||
            ocrStatus === 'pending' ||
            textStatus === 'processing' ||
            textStatus === 'pending' ||
            indexStatus === 'processing' ||
            indexStatus === 'pending'
          )

        // 仅不在处理队列中的文件（已完成/已失败/未处理且未被加入队列）才显示处理按钮
        const canEnqueue =
          doc.doc_type === 'pdf' &&
          !needsOcrConfirm &&
          !isActivelyProcessing &&
          indexStatus !== 'done'

        // 任意阶段检测失败 → 显示重试按钮（重新入队）
        const hasFailedStage =
          doc.doc_type === 'pdf' &&
          (inspectorStatus === 'error' ||
            textStatus === 'error' ||
            ocrStatus === 'error' ||
            moldetStatus === 'error' ||
            indexStatus === 'error')
        const canRetry = hasFailedStage && !isActivelyProcessing

        return (
          <motion.div
            key={doc.doc_id}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.02, duration: 0.2 }}
          >
            <div
              className="project-doc-item"
              onClick={() => onOpenFile(doc)}
              title={moldetHint}
            >
              <FileTextIcon size={14} className="project-doc-icon" />
              <BodyText size="sm" className="project-doc-title">{doc.title || doc.path}</BodyText>
              <div className="project-doc-badges">
                <Badge variant="neutral">{doc.doc_type}</Badge>
                {isInspecting ? <Badge variant="warning">{t('common.detecting')}</Badge> : inspectorBadge}
                {textBadge}
                {ocrBadge}
                {moldetBadge}
                {indexBadge}
                {isActivelyProcessing && !ocrBadge && !textBadge && !indexBadge && (
                  <Badge variant="warning">{t('common.processing')}</Badge>
                )}
              </div>
              {needsOcrConfirm && (
                <div className="project-doc-actions" onClick={(e) => e.stopPropagation()}>
                  <Button
                    variant="primary"
                    size="sm"
                    loading={isConfirming}
                    onClick={() => handleConfirmOcr(doc, true)}
                  >
                    {t('common.confirm')}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={isConfirming}
                    onClick={() => handleConfirmOcr(doc, false)}
                  >
                    {t('common.skip')}
                  </Button>
                </div>
              )}
              {canEnqueue && (
                <div className="project-doc-actions" onClick={(e) => e.stopPropagation()}>
                  <Button
                    variant="primary"
                    size="sm"
                    loading={isEnqueueing}
                    disabled={isEnqueueing}
                    onClick={() => handleEnqueue(doc)}
                  >
                    {t('common.process')}
                  </Button>
                </div>
              )}
              {canRetry && (
                <div className="project-doc-actions" onClick={(e) => e.stopPropagation()}>
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={isEnqueueing}
                    disabled={isEnqueueing}
                    onClick={() => handleEnqueue(doc)}
                  >
                    {t('common.retry')}
                  </Button>
                </div>
              )}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}
