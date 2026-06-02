import { motion } from 'framer-motion'
import type { DocumentEntry } from '../../types'
import PageContainer from '../ui/PageContainer'
import PageTitle from '../ui/PageTitle'
import SectionTitle from '../ui/SectionTitle'
import Card from '../ui/Card'
import IconContainer from '../ui/IconContainer'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import BodyText from '../ui/BodyText'
import Caption from '../ui/Caption'
import Skeleton from '../ui/Skeleton'
import EmptyState from '../ui/EmptyState'
import ResponsiveStatGrid from '../ui/ResponsiveStatGrid'
import AlertBanner from '../ui/AlertBanner'
import { FolderIcon, FileTextIcon, FlaskIcon, ExternalLinkIcon, SettingsIcon } from '../icons'
import { StaggerContainer, StaggerItem } from '../animations/StaggerContainer'

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
  onScan: () => void
  onIndex: () => void
  onOpenFile: (doc: DocumentEntry) => void
  onDismissError: () => void
}

export default function ProjectDashboard({
  projectRoot,
  docs,
  isLoading,
  isIndexing,
  indexProgress,
  indexResult,
  error,
  onScan,
  onIndex,
  onOpenFile,
  onDismissError,
}: Props) {
  const projectName = projectRoot ? projectRoot.split('/').pop() || projectRoot : '未选择项目'

  return (
    <PageContainer>
      {error && <AlertBanner variant="danger" message={error} onDismiss={onDismissError} />}

      {/* 头部 */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '32px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <IconContainer size={48}>
            <FolderIcon size={24} />
          </IconContainer>
          <div>
            <PageTitle style={{ marginBottom: '4px' }}>{projectName}</PageTitle>
            <BodyText muted size="sm">{projectRoot || '请先打开或创建一个项目'}</BodyText>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
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
          >
            项目设置
          </Button>
        </div>
      </div>

      {/* 统计卡片 */}
      <StaggerContainer stagger={0.08}>
        <ResponsiveStatGrid style={{ marginBottom: '32px' }}>
          <StaggerItem>
            <Card>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ color: 'var(--text-muted)' }}><FileTextIcon size={18} /></div>
                <div>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>{String(docs.length)}</div>
                  <Caption>文献</Caption>
                </div>
              </div>
            </Card>
          </StaggerItem>
          <StaggerItem>
            <Card>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ color: 'var(--text-muted)' }}><FlaskIcon size={18} /></div>
                <div>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>{indexResult ? String(indexResult.sections) : '—'}</div>
                  <Caption>Sections</Caption>
                </div>
              </div>
            </Card>
          </StaggerItem>
          <StaggerItem>
            <Card>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ color: 'var(--text-muted)' }}><FileTextIcon size={18} /></div>
                <div>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>{String(docs.filter(d => d.indexed).length)}</div>
                  <Caption>已索引</Caption>
                </div>
              </div>
            </Card>
          </StaggerItem>
          <StaggerItem>
            <Card>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ color: 'var(--text-muted)' }}><FolderIcon size={18} /></div>
                <div>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>{String(docs.length)}</div>
                  <Caption>文件</Caption>
                </div>
              </div>
            </Card>
          </StaggerItem>
        </ResponsiveStatGrid>
      </StaggerContainer>

      {/* 索引进度条 */}
      {isIndexing && indexProgress && (
        <Card padding="14px 18px" style={{ marginBottom: '16px', borderRadius: '10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <BodyText size="sm" style={{ fontWeight: 500 }}>
              正在索引 {indexProgress.current}/{indexProgress.total}
            </BodyText>
            <Caption truncate style={{ maxWidth: '300px' }}>
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
        <Card padding="12px 16px" style={{ marginBottom: '16px', borderRadius: '8px', background: 'rgba(22,163,74,0.1)', borderColor: 'rgba(22,163,74,0.3)' }}>
          <BodyText size="sm" style={{ color: '#16a34a' }}>
            已索引 {indexResult.indexed} 个 PDF，生成 {indexResult.sections} 个 section
          </BodyText>
        </Card>
      )}

      {/* 文件列表 */}
      <SectionTitle style={{ fontSize: '16px', textTransform: 'none', letterSpacing: 'normal', marginBottom: '16px' }}>
        项目文件
      </SectionTitle>

      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <Skeleton variant="row" count={5} height={48} />
        </div>
      ) : docs.length === 0 ? (
        <EmptyState
          message={projectRoot ? '暂无文件，点击"扫描文件"索引项目内容' : '请先打开或创建一个项目'}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {docs.map((doc, index) => {
            const delayedFadeUp = {
              hidden: { opacity: 0, y: 6 },
              visible: {
                opacity: 1,
                y: 0,
                transition: { delay: index * 0.03, duration: 0.3 }
              },
            }
            return (
              <motion.div
                key={doc.doc_id}
                variants={delayedFadeUp}
                initial="hidden"
                animate="visible"
              >
                <Card
                  onClick={() => onOpenFile(doc)}
                  style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 16px', borderRadius: '8px' }}
                >
                  <FileTextIcon size={16} />
                  <BodyText size="md" style={{ flex: 1 }}>{doc.title || doc.path}</BodyText>
                  <Badge variant="neutral">{doc.doc_type}</Badge>
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
      )}
    </PageContainer>
  )
}
