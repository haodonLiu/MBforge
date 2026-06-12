import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import Card from '../ui/Card'
import BodyText from '../ui/BodyText'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import Skeleton from '../ui/Skeleton'
import EmptyState from '../ui/EmptyState'
import { FileTextIcon } from '../icons'
import { inspectPdf, confirmOcr } from '../../api/tauri/pdf'
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
  const inspectedRef = useRef<Set<string>>(new Set())
  const [inspectingIds, setInspectingIds] = useState<Set<string>>(new Set())
  const [confirmingIds, setConfirmingIds] = useState<Set<string>>(new Set())

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
          .catch((e) => {
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
      showToast(confirm ? '已确认 OCR，将加入处理队列' : '已跳过 OCR', 'success')
      onRefreshDocs?.()
    } catch (e) {
      console.error('[DocumentList] confirm OCR failed:', e)
      showToast('OCR 确认失败: ' + String(e), 'error')
    } finally {
      setConfirmingIds(prev => {
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
        message={projectRoot ? '暂无文件，点击"扫描文件"索引项目内容' : '请先打开或创建一个项目'}
      />
    )
  }

  return (
    <div className="project-doc-list">
      {docs.map((doc, index) => {
        const delayedFadeUp = {
          hidden: { opacity: 0, y: 6 },
          visible: {
            opacity: 1,
            y: 0,
            transition: { delay: index * 0.03, duration: 0.3 }
          },
        }

        const isInspecting = inspectingIds.has(doc.doc_id)
        const isConfirming = confirmingIds.has(doc.doc_id)

        const inspectorStatus = doc.inspector_status || 'pending'
        const inspectorBadge =
          doc.doc_type !== 'pdf'
            ? null
            : inspectorStatus === 'text_based'
              ? <Badge variant="success">文本型</Badge>
              : inspectorStatus === 'scanned'
                ? <Badge variant="warning">扫描件</Badge>
                : inspectorStatus === 'mixed'
                  ? <Badge variant="warning">混合</Badge>
                  : inspectorStatus === 'image_based'
                    ? <Badge variant="neutral">图像型</Badge>
                    : inspectorStatus === 'error'
                      ? <Badge variant="danger">检测失败</Badge>
                      : <Badge variant="neutral">待检测</Badge>

        const textStatus = doc.text_status || 'pending'
        const textBadge =
          doc.doc_type !== 'pdf'
            ? null
            : textStatus === 'done'
              ? <Badge variant="success">已提取</Badge>
              : textStatus === 'error'
                ? <Badge variant="danger">提取失败</Badge>
                : <Badge variant="neutral">未提取</Badge>

        const ocrStatus = doc.ocr_status || 'not_processed'
        const ocrBadge =
          doc.doc_type !== 'pdf'
            ? null
            : ocrStatus === 'done' || ocrStatus === 'completed'
              ? <Badge variant="success">已 OCR</Badge>
              : ocrStatus === 'processing'
                ? <Badge variant="warning">OCR 中</Badge>
              : ocrStatus === 'pending'
                ? <Badge variant="warning">等待 OCR</Badge>
              : ocrStatus === 'pending_confirmation'
                ? <Badge variant="warning">待确认 OCR</Badge>
              : ocrStatus === 'skipped'
                ? <Badge variant="neutral">已跳过 OCR</Badge>
              : ocrStatus === 'error'
                ? <Badge variant="danger">OCR 失败</Badge>
                : <Badge variant="neutral">未 OCR</Badge>

        const moldetStatus = doc.moldet_status || 'not_processed'
        const moldetBadge =
          doc.doc_type !== 'pdf'
            ? null
            : moldetStatus === 'has_molecule'
              ? <Badge variant="success">含分子</Badge>
              : moldetStatus === 'no_molecule'
                ? <Badge variant="neutral">无分子</Badge>
                : moldetStatus === 'error'
                  ? <Badge variant="danger">扫描失败</Badge>
                  : <Badge variant="neutral">未扫描</Badge>

        const indexStatus = doc.index_status || 'pending'
        const indexBadge =
          doc.doc_type !== 'pdf'
            ? null
            : indexStatus === 'done'
              ? <Badge variant="success">已索引</Badge>
              : indexStatus === 'error'
                ? <Badge variant="danger">索引失败</Badge>
                : <Badge variant="neutral">未索引</Badge>

        const moldetHint =
          doc.doc_type === 'pdf' && doc.moldet_pages && doc.moldet_pages.length > 0
            ? `分子页: ${doc.moldet_pages.join(', ')}`
            : undefined

        const needsOcrConfirm = doc.doc_type === 'pdf' && ocrStatus === 'pending_confirmation'

        return (
          <motion.div
            key={doc.doc_id}
            variants={delayedFadeUp}
            initial="hidden"
            animate="visible"
          >
            <Card
              onClick={() => onOpenFile(doc)}
              className="project-doc-item"
              title={moldetHint}
            >
              <FileTextIcon size={16} />
              <BodyText size="md" className="project-doc-title">{doc.title || doc.path}</BodyText>
              <Badge variant="neutral">{doc.doc_type}</Badge>
              {isInspecting ? <Badge variant="warning">检测中...</Badge> : inspectorBadge}
              {textBadge}
              {ocrBadge}
              {moldetBadge}
              {indexBadge}
              {needsOcrConfirm && (
                <div
                  style={{ display: 'inline-flex', gap: '8px', marginLeft: 'auto' }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <Button
                    variant="primary"
                    size="sm"
                    loading={isConfirming}
                    onClick={() => handleConfirmOcr(doc, true)}
                  >
                    确认 OCR
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={isConfirming}
                    onClick={() => handleConfirmOcr(doc, false)}
                  >
                    跳过
                  </Button>
                </div>
              )}
            </Card>
          </motion.div>
        )
      })}
    </div>
  )
}
