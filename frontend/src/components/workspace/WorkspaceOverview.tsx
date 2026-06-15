import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { motion } from 'framer-motion'
import { ResponsiveStatGrid, EmptyState } from '@/components/ui'
import { FileTextIcon, FlaskIcon } from '@/components/icons'
import DashboardStatCard from '@/components/dashboard/DashboardStatCard'
import { useAppContext } from '@/context/AppContext'
import { showToast } from '@/hooks/useToast'
import { listProjectDocuments } from '@/api/tauri/project'
import { moleculeStatsTauri } from '@/api/tauri/molecule'
import { fadeUp } from '@/hooks/useAnimations'

interface WorkspaceStats {
  documents: number
  indexed: number
  molecules: number
  confirmed: number
}

/**
 * Workspace 概览页。
 *
 * 展示项目关键统计指标，当前以文献与分子数据为主。
 */
export default function WorkspaceOverview() {
  const { t } = useTranslation()
  const { projectRoot } = useAppContext()
  const [stats, setStats] = useState<WorkspaceStats>({
    documents: 0,
    indexed: 0,
    molecules: 0,
    confirmed: 0,
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadStats = async () => {
      if (!projectRoot) {
        setLoading(false)
        return
      }
      setLoading(true)
      try {
        const [docResp, molResp] = await Promise.all([
          listProjectDocuments(projectRoot),
          moleculeStatsTauri(projectRoot),
        ])
        const docs = docResp.documents
        const indexed = docs.filter((d) => d.indexed).length
        const molStats = molResp.success ? molResp.stats : { total: 0, pending: 0 }
        setStats({
          documents: docs.length,
          indexed,
          molecules: molStats.total,
          confirmed: molStats.total - (molStats.pending ?? 0),
        })
      } catch {
        showToast(t('workspace.loadStatsFailed'), 'error')
      } finally {
        setLoading(false)
      }
    }

    void loadStats()
  }, [projectRoot, t])

  if (!projectRoot) {
    return (
      <div className="workspace-overview">
        <EmptyState message={t('workspace.noProjectSelected')} />
      </div>
    )
  }

  if (loading) {
    return (
      <div className="workspace-overview">
        <EmptyState message={t('common.loading')} />
      </div>
    )
  }

  return (
    <motion.div
      className="workspace-overview"
      variants={fadeUp}
      initial="hidden"
      animate="visible"
    >
      <ResponsiveStatGrid className="stat-grid">
        <DashboardStatCard
          label={t('workspace.totalDocuments')}
          value={stats.documents}
          subValue={`${stats.indexed} ${t('workspace.indexedDocuments')}`}
          icon={<FileTextIcon size={18} />}
          color="var(--info)"
        />
        <DashboardStatCard
          label={t('mol.title')}
          value={stats.molecules}
          subValue={`${stats.confirmed} ${t('dashboard.confirmed')}`}
          icon={<FlaskIcon size={18} />}
          color="var(--accent)"
          delay={0.05}
        />
      </ResponsiveStatGrid>
    </motion.div>
  )
}
