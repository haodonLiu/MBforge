import { motion } from 'framer-motion'
import Card from '../ui/Card'
import BodyText from '../ui/BodyText'
import Badge from '../ui/Badge'
import Skeleton from '../ui/Skeleton'
import EmptyState from '../ui/EmptyState'
import { FileTextIcon } from '../icons'
import type { DocumentEntry } from '../../types'

interface DocumentListProps {
  docs: DocumentEntry[]
  isLoading: boolean
  projectRoot: string
  onOpenFile: (doc: DocumentEntry) => void
}

export default function DocumentList({ docs, isLoading, projectRoot, onOpenFile }: DocumentListProps) {
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

        const ocrStatus = doc.ocr_status || 'not_processed'
        const ocrBadge =
          doc.doc_type !== 'pdf'
            ? null
            : ocrStatus === 'completed'
              ? <Badge variant="success">已 OCR</Badge>
              : ocrStatus === 'processing'
                ? <Badge variant="warning">OCR 中</Badge>
                : ocrStatus === 'error'
                  ? <Badge variant="danger">OCR 失败</Badge>
                  : <Badge variant="neutral">未 OCR</Badge>

        return (
          <motion.div
            key={doc.doc_id}
            variants={delayedFadeUp}
            initial="hidden"
            animate="visible"
          >
            <Card onClick={() => onOpenFile(doc)} className="project-doc-item">
              <FileTextIcon size={16} />
              <BodyText size="md" className="project-doc-title">{doc.title || doc.path}</BodyText>
              <Badge variant="neutral">{doc.doc_type}</Badge>
              {ocrBadge}
              {doc.indexed ? (
                <Badge variant="success">已索引</Badge>
              ) : (
                <Badge variant="neutral">未索引</Badge>
              )}
            </Card>
          </motion.div>
        )
      })}
    </div>
  )
}
