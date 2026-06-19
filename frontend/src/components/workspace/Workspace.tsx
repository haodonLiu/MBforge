import { useCallback, useState } from 'react'
import { motion } from 'framer-motion'
import { fadeUp } from '@/hooks/useAnimations'
import ProjectView from '@/components/ProjectView'

/**
 * Workspace 页面。
 *
 * 当无文件打开时显示项目仪表盘，打开文件（PDF/Markdown）时隐藏标题，
 * 让文件查看器占据全部空间。
 */
export default function Workspace() {
  const [fileActive, setFileActive] = useState(false)
  const handleFileActive = useCallback((active: boolean) => setFileActive(active), [])

  return (
    <motion.div
      className="workspace-page"
      variants={fadeUp}
      initial="hidden"
      animate="visible"
      style={fileActive ? { padding: 0, gap: 0 } : undefined}
    >
      {!fileActive && (
        <div className="workspace-header">
        </div>
      )}

      {/* Document browser */}
      <div className="workspace-content">
        <ProjectView onFileActive={handleFileActive} />
      </div>
    </motion.div>
  )
}
