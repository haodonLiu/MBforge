import { motion } from 'framer-motion'
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
import { FolderIcon, FlaskIcon, ExternalLinkIcon, SettingsIcon } from '../icons'
import ScanWarningsPanel from './ScanWarningsPanel'
import ProjectStats from './ProjectStats'
import FolderLayoutCard from './FolderLayoutCard'
import DocumentList from './DocumentList'

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
  error: string
  scanWarnings: ScanWarning[]
  onScan: () => void
  onIndex: () => void
  onOpenFile: (doc: DocumentEntry) => void
  onDismissError: () => void
  onDismissWarnings: () => void
  onSettingsOpen: () => void
}

export default function ProjectDashboard({
  projectRoot,
  docs,
  isLoading,
  isIndexing,
  indexProgress,
  indexResult,
  error,
  scanWarnings,
  onScan,
  onIndex,
  onOpenFile,
  onDismissError,
  onDismissWarnings,
  onSettingsOpen,
}: Props) {
  const projectName = projectRoot ? projectRoot.split('/').pop() || projectRoot : '未选择项目'

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
            disabled={!projectRoot || isLoading || isIndexing}
            loading={isLoading}
          >
            {isLoading ? '扫描中...' : '扫描文件'}
          </Button>
          <Button
            variant="secondary"
            size="md"
            icon={<FlaskIcon size={14} />}
            onClick={onIndex}
            disabled={!projectRoot || isLoading || isIndexing}
            loading={isIndexing}
          >
            {isIndexing ? '索引中...' : '索引文件'}
          </Button>
          <Button
            variant="secondary"
            size="md"
            icon={<SettingsIcon size={14} />}
            onClick={onSettingsOpen}
          >
            项目设置
          </Button>
        </div>
      </div>

      <ProjectStats docs={docs} indexResult={indexResult} />

      <FolderLayoutCard projectRoot={projectRoot} />

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
      />
    </PageContainer>
  )
}
