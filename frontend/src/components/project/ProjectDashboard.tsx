import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { DocumentEntry } from '../../types'
import type { ScanWarning } from '../../api/tauri'
import PageContainer from '../ui/PageContainer'
import BodyText from '../ui/BodyText'
import Button from '../ui/Button'
import Caption from '../ui/Caption'
import IconButton from '../ui/IconButton'
import Card from '../ui/Card'
import IconContainer from '../ui/IconContainer'
import AlertBanner from '../ui/AlertBanner'
import { FolderIcon, FlaskIcon, ExternalLinkIcon, SettingsIcon, SearchIcon, FileTextIcon } from '../icons'
import ScanWarningsPanel from './ScanWarningsPanel'
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
  isSyncing: boolean
  syncStage: 'scanning' | 'indexing' | null
  indexProgress: IndexProgress | null
  indexResult: { indexed: number; sections: number } | null
  isMoldetScanning: boolean
  moldetProgress: { current: number; total: number } | null
  moldetResult: { scanned: number; withMolecules: number } | null
  error: string
  scanWarnings: ScanWarning[]
  moleculeStats: { total: number; confirmed: number } | null
  onSync: () => void
  onMoldetScan: () => void
  onOpenFile: (doc: DocumentEntry) => void
  onDismissError: () => void
  onDismissWarnings: () => void
  onRefreshDocs?: () => void
}

export default function ProjectDashboard({
  projectRoot,
  docs,
  isLoading,
  isSyncing,
  syncStage,
  indexProgress,
  indexResult,
  isMoldetScanning,
  moldetProgress,
  moldetResult,
  error,
  scanWarnings,
  moleculeStats,
  onSync,
  onMoldetScan,
  onOpenFile,
  onDismissError,
  onDismissWarnings,
  onRefreshDocs,
}: Props) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const projectName = projectRoot ? projectRoot.split('/').pop() || projectRoot : t('workspace.noProjectSelected')
  const indexedCount = docs.filter(d => d.indexed).length
  const totalDocs = docs.length
  const totalSections = indexResult?.sections ?? 0
  const totalMolecules = moleculeStats?.total ?? 0
  const confirmedMolecules = moleculeStats?.confirmed ?? 0

  return (
    <PageContainer noPadding style={{ padding: '20px 24px' }}>
      <div className="project-dashboard">
        {error && <AlertBanner variant="danger" message={error} onDismiss={onDismissError} />}
        <ScanWarningsPanel warnings={scanWarnings} onDismiss={onDismissWarnings} />

        {/* Header: project name + actions */}
        <div className="project-dashboard-header">
          <div className="project-dashboard-title-row">
            <IconContainer size={40}>
              <FolderIcon size={20} />
            </IconContainer>
            <div>
              <BodyText size="lg" className="project-dashboard-name" style={{ fontWeight: 600 }}>
                {projectName}
              </BodyText>
              <Caption>{projectRoot || t('project.noProject')}</Caption>
            </div>
          </div>
          <div className="project-dashboard-actions">
            <Button
              variant="primary"
              size="sm"
              icon={<ExternalLinkIcon size={14} />}
              onClick={onSync}
              disabled={!projectRoot || isSyncing || isMoldetScanning}
              loading={isSyncing}
            >
              {isSyncing
                ? syncStage === 'scanning'
                  ? t('project.syncScanning')
                  : t('project.syncIndexing')
                : t('project.sync')}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={<SearchIcon size={14} />}
              onClick={onMoldetScan}
              disabled={!projectRoot || isSyncing || isMoldetScanning}
              loading={isMoldetScanning}
            >
              {isMoldetScanning ? t('project.detectingMolecules') : t('project.detectMolecules')}
            </Button>
            <IconButton
              title={t('nav.settings')}
              onClick={() => void navigate('/settings')}
              size={32}
            >
              <SettingsIcon size={18} />
            </IconButton>
          </div>
        </div>

        {/* Stats row */}
        <div className="project-stats-row">
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0 }}
          >
            <div className="project-stat-card">
              <div className="project-stat-icon">
                <FileTextIcon size={18} />
              </div>
              <div className="project-stat-info">
                <div className="project-stat-value">{totalDocs}</div>
                <div className="project-stat-label">{t('project.documents')}</div>
              </div>
            </div>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
          >
            <div className="project-stat-card">
              <div className="project-stat-icon">
                <FlaskIcon size={18} />
              </div>
              <div className="project-stat-info">
                <div className="project-stat-value">{totalSections}</div>
                <div className="project-stat-label">Sections</div>
              </div>
            </div>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <div className="project-stat-card">
              <div className="project-stat-icon">
                <FolderIcon size={18} />
              </div>
              <div className="project-stat-info">
                <div className="project-stat-value">{indexedCount}/{totalDocs}</div>
                <div className="project-stat-label">{t('project.indexed')}</div>
              </div>
            </div>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
          >
            <div className="project-stat-card">
              <div className="project-stat-icon">
                <FlaskIcon size={18} />
              </div>
              <div className="project-stat-info">
                <div className="project-stat-value">{totalMolecules}</div>
                <div className="project-stat-label">{t('project.molecules')}{confirmedMolecules > 0 ? ` ${t('project.moleculesConfirmed', { count: confirmedMolecules })}` : ''}</div>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Scrollable content area */}
        <div className="project-dashboard-content">
          {/* Progress indicators */}
          {isMoldetScanning && moldetProgress && (
            <Card padding="12px 16px" className="project-index-progress">
              <div className="project-index-progress-header">
                <BodyText size="sm" className="project-index-progress-title">
                  {t('project.scanningMoldet', { current: moldetProgress.current, total: moldetProgress.total })}
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
            <Card padding="10px 14px" className="project-index-success">
              <BodyText size="sm">
                {t('project.moldetComplete', { scanned: moldetResult.scanned, withMolecules: moldetResult.withMolecules })}
              </BodyText>
            </Card>
          )}

          {isSyncing && syncStage === 'indexing' && indexProgress && (
            <Card padding="12px 16px" className="project-index-progress">
              <div className="project-index-progress-header">
                <BodyText size="sm" className="project-index-progress-title">
                  {t('project.syncIndexingProgress', { current: indexProgress.current, total: indexProgress.total })}
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
            <Card padding="10px 14px" className="project-index-success">
              <BodyText size="sm">
                {t('project.indexComplete', { indexed: indexResult.indexed, sections: indexResult.sections })}
              </BodyText>
            </Card>
          )}

          {/* Document list */}
          <div className="project-docs-section">
            <div className="project-docs-header">
              <BodyText size="sm" className="project-docs-title">{t('project.projectFiles')}</BodyText>
              {totalDocs > 0 && (
                <Caption className="project-docs-count">{t('project.fileCount', { count: totalDocs })}</Caption>
              )}
            </div>
            <DocumentList
              docs={docs}
              isLoading={isLoading}
              projectRoot={projectRoot}
              onOpenFile={onOpenFile}
              onRefreshDocs={onRefreshDocs}
            />
          </div>
        </div>
      </div>
    </PageContainer>
  )
}
