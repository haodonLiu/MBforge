import { useState, useEffect } from 'react'
import { listDocuments, scanProject } from '../api/client'
import { indexProjectRust, type IndexResult } from '../api/tauri-bridge'
import { listen } from '@tauri-apps/api/event'
import { FolderIcon, FileTextIcon, FlaskIcon, ExternalLinkIcon, SettingsIcon, ArrowLeftIcon } from './icons'
import type { DocumentEntry } from '../types'
import { getProjectRoot } from '../hooks/useProjectRoot'
import ErrorBanner from './ErrorBanner'
import { motion } from 'framer-motion'
import { StaggerContainer, StaggerItem } from './animations/StaggerContainer'

import PageContainer from '../components/ui/PageContainer'
import PageTitle from '../components/ui/PageTitle'
import SectionTitle from '../components/ui/SectionTitle'
import Card from '../components/ui/Card'
import HoverCard from '../components/ui/HoverCard'
import CardGrid from '../components/ui/CardGrid'
import IconContainer from '../components/ui/IconContainer'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import BodyText from '../components/ui/BodyText'
import Caption from '../components/ui/Caption'
import Skeleton from '../components/ui/Skeleton'
import EmptyState from '../components/ui/EmptyState'
import Toolbar from '../components/ui/Toolbar'
import IconButton from '../components/ui/IconButton'

export default function ProjectView() {
  const [projectRoot, setProjectRoot] = useState(getProjectRoot())
  const [docs, setDocs] = useState<DocumentEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isIndexing, setIsIndexing] = useState(false)
  const [indexProgress, setIndexProgress] = useState<{ file: string; current: number; total: number } | null>(null)
  const [indexResult, setIndexResult] = useState<{ indexed: number; sections: number } | null>(null)
  const [error, setError] = useState('')

  // PDF 阅读状态
  const [selectedPdf, setSelectedPdf] = useState<DocumentEntry | null>(null)

  const loadDocs = async () => {
    const root = getProjectRoot()
    if (!root) return
    setIsLoading(true)
    setError('')
    try {
      const resp = await listDocuments(root)
      if (resp.success && resp.documents) {
        setDocs(resp.documents)
      } else {
        setError(resp.error || 'Failed to load documents')
      }
    } catch (e) {
      console.error(e)
      setError('Failed to load documents')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    setProjectRoot(getProjectRoot())
    loadDocs()
  }, [])

  const handleScan = async () => {
    const root = getProjectRoot()
    if (!root) return
    setIsLoading(true)
    setError('')
    try {
      const resp = await scanProject(root)
      if (resp.success && resp.documents) {
        setDocs(resp.documents)
      } else {
        setError(resp.error || 'Scan failed')
      }
    } catch (e) {
      console.error(e)
      setError('Scan failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleIndex = async () => {
    const root = getProjectRoot()
    if (!root) return
    setIsIndexing(true)
    setError('')
    setIndexResult(null)
    setIndexProgress(null)

    // Scan first
    scanProject(root).then(scanResp => {
      if (scanResp.success && scanResp.documents) setDocs(scanResp.documents)
    }).catch(() => {})

    // Listen for progress events from Rust
    let total = 0
    const unlisten = await listen<{ stage: string; payload: Record<string, unknown> }>('doc-progress', (event) => {
      const payload = event.payload.payload
      const parser = payload.parser as string || ''
      if (parser.startsWith('indexing')) {
        const match = parser.match(/indexing\s+(\d+)\/(\d+)/)
        if (match) {
          const current = parseInt(match[1], 10)
          total = parseInt(match[2], 10)
          setIndexProgress({ file: parser, current, total })
        }
      }
    })

    try {
      const result: IndexResult = await indexProjectRust(root)
      setIndexResult({ indexed: result.indexed, sections: result.sections })
      if (result.errors.length > 0) {
        console.warn('Index errors:', result.errors)
      }
      listDocuments(root).then(r => { if (r.success && r.documents) setDocs(r.documents) })
    } catch (e) {
      setError(String(e))
    } finally {
      unlisten()
      setIndexProgress(null)
      setIsIndexing(false)
    }
  }

  const handleOpenPdf = (doc: DocumentEntry) => {
    if (doc.doc_type === 'pdf') {
      setSelectedPdf(doc)
    }
  }

  const handleClosePdf = () => {
    setSelectedPdf(null)
  }

  const projectName = projectRoot ? projectRoot.split('/').pop() || projectRoot : '未选择项目'

  // PDF 视图
  if (selectedPdf) {
    const pdfUrl = `/api/v1/file/pdf?path=${encodeURIComponent(selectedPdf.path)}`
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
        {/* 工具栏 */}
        <Toolbar style={{ justifyContent: 'flex-start', gap: '12px', height: '48px', padding: '0 16px' }}>
          <IconButton size={32} onClick={handleClosePdf}>
            <ArrowLeftIcon size={18} />
          </IconButton>
          <Caption truncate style={{ fontSize: '13px', fontWeight: 500 }}>
            {selectedPdf.title || selectedPdf.path}
          </Caption>
        </Toolbar>
        {/* PDF 内容 */}
        <iframe
          src={pdfUrl}
          title={selectedPdf.title || 'PDF'}
          style={{
            flex: 1,
            width: '100%',
            border: 'none',
            background: '#525659',
          }}
        />
      </div>
    )
  }

  // 项目视图
  return (
    <PageContainer>
      {error && <ErrorBanner message={error} onDismiss={() => setError('')} />}

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
            onClick={handleScan}
            disabled={!projectRoot || isLoading || isIndexing}
            loading={isLoading}
          >
            {isLoading ? '扫描中...' : '扫描文件'}
          </Button>
          <Button
            variant="secondary"
            size="md"
            icon={<FlaskIcon size={14} />}
            onClick={handleIndex}
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
        <CardGrid style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginBottom: '32px' }}>
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
        </CardGrid>
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
          {docs.map((doc, index) => (
            <motion.div
              key={doc.doc_id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.03, duration: 0.3 }}
            >
              <HoverCard
                onClick={() => handleOpenPdf(doc)}
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
              </HoverCard>
            </motion.div>
          ))}
        </div>
      )}
    </PageContainer>
  )
}
