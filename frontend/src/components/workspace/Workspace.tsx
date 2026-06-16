import { useTranslation } from 'react-i18next'
import { motion } from 'framer-motion'
import { PageTitle } from '@/components/ui'
import { fadeUp } from '@/hooks/useAnimations'
import ProjectView from '@/components/ProjectView'

/**
 * Workspace 页面。
 *
 * 合并概览与文档：顶部统计卡片 + 下方文档浏览器。
 */
export default function Workspace() {
  const { t } = useTranslation()

  return (
    <motion.div
      className="workspace-page"
      variants={fadeUp}
      initial="hidden"
      animate="visible"
    >
      <div className="workspace-header">
        <PageTitle>{t('workspace.title')}</PageTitle>
      </div>

      {/* Document browser */}
      <div className="workspace-content">
        <ProjectView />
      </div>
    </motion.div>
  )
}
