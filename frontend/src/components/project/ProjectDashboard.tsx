import { motion } from 'framer-motion'
import { useState } from 'react'
import type { DocumentEntry } from '../../types'
import type { ScanWarning } from '../../api/tauri'
import PageContainer from '../ui/PageContainer'
import PageTitle from '../ui/PageTitle'
import SectionTitle from '../ui/SectionTitle'
import BodyText from '../ui/BodyText'
import Button from '../ui/Button'
import Caption from '../ui/Caption'
import Card from '../ui/Card'
import IconContainer from '../ui/IconContainer'
import AlertBanner from '../ui/AlertBanner'
import { FolderIcon, FlaskIcon, ExternalLinkIcon, SettingsIcon, SearchIcon, QueueIcon } from '../icons'
import ScanWarningsPanel from './ScanWarningsPanel'
import ProjectStats from './ProjectStats'
import FolderLayoutCard from './FolderLayoutCard'
import DocumentList from './DocumentList'
import ProcessingQueue from './ProcessingQueue'

interface IndexProgress {
  file: string
  current: number
  total: number
}

interface Props {
  projectRoot: string
  docs: DocumentEntry[]
  isLoading: boolean
  isIndexing: boolean
  indexProgress: IndexProgress | null
  indexResult: { indexed: number; sections: number } | null
  isMoldetScanning: boolean
  moldetProgress: { current: number; total: number } | null
  moldetResult: { scanned: number; withMolecules: number } | null
  error: string
  scanWarnings: ScanWarning[]
  onScan: () => void
  onIndex: () => void
  onMoldetScan: () => void
  onOpenFile: (doc: DocumentEntry) => void
  onDismissError: () => void
  onDismissWarnings: () => void
  onSettingsOpen: () => void
  onRefreshDocs?: () => void
}

export default function ProjectDashboard({
  projectRoot,
  docs,
  isLoading,
  isIndexing,
  indexProgress,
  indexResult,
  isMoldetScanning,
  moldetProgress,
  moldetResult,
  error,
  scanWarnings,
  onScan,
  onIndex,
  onMoldetScan,
  onOpenFile,
  onDismissError,
  onDismissWarnings,
  onSettingsOpen,
  onRefreshDocs,
}: Props) {
  const projectName = projectRoot ? projectRoot.split('/').pop() || projectRoot : '未选择项目'
  const [showQueue, setShowQueue] = useState(false)

  return (
    <PageContainer>
      {error && <AlertBanner variant="danger" message={error} onDismiss={onDismissError} />}

      <ScanWarningsPanel warnings={scanWarnings} onDismiss={onDismissWarnings} />

      <div className="project-dashboard-header">
        <div className="project-dashboard-title-row">
          <IconContainer size={48}>
            <FolderIcon size={24} />
          </IconContainer>
          <div>
            <PageTitle className="project-dashboard-name">{projectName}</PageTitle>
            <BodyText muted size="sm">{projectRoot || '请先打开或创建一个项目'}</BodyText>
          </div>
        </div>
        <div className="project-dashboard-actions">
          <Button
            variant="secondary"
            size="md"
            icon={<ExternalLinkIcon size={14} />}
            onClick={onScan}
            disabled={!projectRoot || isLoading || isIndexing || isMoldetScanning}
            loading={isLoading}
          >
            {isLoading ? '扫描中...' : '扫描文件'}
          </Button>
          <Button
            variant="secondary"
            size="md"
            icon={<FlaskIcon size={14} />}
            onClick={onIndex}
            disabled={!projectRoot || isLoading || isIndexing || isMoldetScanning}
            loading={isIndexing}
          >
            {isIndexing ? '索引中...' : '索引文件'}
          </Button>
          <Button
            variant="secondary"
            size="md"
            icon={<SearchIcon size={14} />}
            onClick={onMoldetScan}
            disabled={!projectRoot || isLoading || isIndexing || isMoldetScanning}
            loading={isMoldetScanning}
          >
            {isMoldetScanning ? '扫描分子中...' : '快速分子扫描'}
          </Button>
          <Button
            variant="secondary"
            size="md"
            icon={<SettingsIcon size={14} />}
            onClick={onSettingsOpen}
          >
            项目设置
          </Button>
          <Button
            variant="secondary"
            size="md"
            icon={<QueueIcon size={14} />}
            onClick={() => setShowQueue((s) => !s)}
          >
            {showQueue ? '隐藏队列' : '处理队列'}
          </Button>
        </div>
      </div>

      {showQueue && (
        <ProcessingQueue projectRoot={projectRoot} />
      )}

      <ProjectStats docs={docs} indexResult={indexResult} />

      <FolderLayoutCard projectRoot={projectRoot} />

      {isMoldetScanning && moldetProgress && (
        <Card padding="14px 18px" className="project-index-progress">
          <div className="project-index-progress-header">
            <BodyText size="sm" className="project-index-progress-title">
              正在快速分子扫描 {moldetProgress.current}/{moldetProgress.total}
            </BodyText>
          </div>
          <div className="download-progress-bar">
            <motion.div
              className="download-progress-fill shimmer"
              style={{ width: `${moldetProgress.total > 0 ? Math.round(moldetProgress.current * 100 / moldetProgress.total) : 0}%` }}
              animate={{ backgroundPosition: ['0% 0%', '100% 0%'] }}
              transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
            />
          </div>
        </Card>
      )}

      {moldetResult && (
        <Card padding="12px 16px" className="project-index-success">
          <BodyText size="sm">
            快速分子扫描完成：已扫描 {moldetResult.scanned} 个 PDF，{moldetResult.withMolecules} 个文档含分子
          </BodyText>
        </Card>
      )}

      {isIndexing && indexProgress && (
        <Card padding="14px 18px" className="project-index-progress">
          <div className="project-index-progress-header">
            <BodyText size="sm" className="project-index-progress-title">
              正在索引 {indexProgress.current}/{indexProgress.total}
            </BodyText>
            <Caption truncate className="project-index-progress-file">
              {indexProgress.file}
            </Caption>
          </div>
          <div className="download-progress-bar">
            <motion.div
              className="download-progress-fill shimmer"
              style={{ width: `${Math.round(indexProgress.current * 100 / indexProgress.total)}%` }}
              animate={{ backgroundPosition: ['0% 0%', '100% 0%'] }}
              transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
            />
          </div>
        </Card>
      )}

      {indexResult && indexResult.indexed > 0 && (
        <Card padding="12px 16px" className="project-index-success">
          <BodyText size="sm">
            已索引 {indexResult.indexed} 个 PDF，生成 {indexResult.sections} 个 section
          </BodyText>
        </Card>
      )}

      <SectionTitle className="project-docs-title">项目文件</SectionTitle>

      <DocumentList
        docs={docs}
        isLoading={isLoading}
        projectRoot={projectRoot}
        onOpenFile={onOpenFile}
        onRefreshDocs={onRefreshDocs}
      />
    </PageContainer>
  )
}
