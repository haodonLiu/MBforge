import { useState } from 'react'
import { motion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { openProject } from '../api/tauri'
import { FolderIcon, MoleculeLogo, TrashIcon, XIcon } from './icons'
import { StaggerContainer, StaggerItem } from './animations/StaggerContainer'
import { showToast } from '../hooks/useToast'
import {
  fadeIn,
  logoEntrance,
  projectCardHover,
  tapScale,
} from '../hooks/useAnimations'
import Button from '../components/ui/Button'
import IconButton from '../components/ui/IconButton'
import PageTitle from '../components/ui/PageTitle'
import SectionTitle from '../components/ui/SectionTitle'
import BodyText from '../components/ui/BodyText'
import Caption from '../components/ui/Caption'
import CreateProjectPage from './welcome/CreateProjectPage'
import OpenProjectPage from './welcome/OpenProjectPage'
import { loadRecent, persistRecent, removeRecentFromStorage } from './welcome/utils'

interface Props {
  onProjectOpened?: (root: string) => void
}

type Page = 'home' | 'create' | 'open'

export default function Welcome({ onProjectOpened }: Props) {
  const { t } = useTranslation()
  const [page, setPage] = useState<Page>('home')
  const [selectedDir, setSelectedDir] = useState('')
  const [projectName, setProjectName] = useState('')
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [recentProjects, setRecentProjects] = useState(() => loadRecent())

  const handleProjectSuccess = (root: string, name: string) => {
    // localStorage persistence is handled by App.tsx via a useEffect on
    // projectRoot, so we do not write it here. We only manage the
    // recent-projects list (separate localStorage key).
    persistRecent(root, name)
    onProjectOpened?.(root)
  }

  const openByName = async (path: string) => {
    setLoading(true)
    try {
      const resp = await openProject(path)
      if (resp.success) {
        handleProjectSuccess(resp.project.root, resp.project.name)
      } else {
        showToast(resp.error || t('welcome.openProject') + ' ' + t('common.noResults'), 'error')
      }
    } catch (e) {
      showToast(`打开失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!selectedDir.trim() || !projectName.trim()) return
    const fullPath = `${selectedDir.trim()}/${projectName.trim()}`
    setLoading(true)
    try {
      const resp = await openProject(fullPath, projectName.trim())
      if (resp.success) {
        handleProjectSuccess(resp.project.root, resp.project.name)
      } else {
        showToast(resp.error || t('common.save') + ' ' + t('common.noResults'), 'error')
      }
    } catch (e) {
      showToast(`创建失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleOpenDir = async () => {
    if (!selectedDir.trim()) return
    setLoading(true)
    try {
      const resp = await openProject(selectedDir.trim())
      if (resp.success) {
        handleProjectSuccess(resp.project.root, resp.project.name)
      } else {
        showToast(resp.error || t('welcome.openProject') + ' ' + t('common.noResults'), 'error')
      }
    } catch (e) {
      showToast(`打开失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  if (page === 'create') {
    return (
      <CreateProjectPage
        selectedDir={selectedDir}
        projectName={projectName}
        loading={loading}
        onDirChange={setSelectedDir}
        onNameChange={setProjectName}
        onCreate={handleCreate}
        onCancel={() => { setPage('home'); setSelectedDir(''); setProjectName('') }}
      />
    )
  }

  if (page === 'open') {
    return (
      <OpenProjectPage
        selectedDir={selectedDir}
        loading={loading}
        onDirChange={setSelectedDir}
        onOpen={handleOpenDir}
        onCancel={() => { setPage('home'); setSelectedDir('') }}
      />
    )
  }

  return (
    <motion.div
      variants={fadeIn}
      initial="hidden"
      animate="visible"
      className="welcome-home"
    >
      <div className="welcome-home-inner">
        <StaggerContainer stagger={0.08}>
          <StaggerItem>
            <motion.div
              variants={logoEntrance}
              initial="hidden"
              animate="visible"
              className="welcome-logo"
            >
              <MoleculeLogo size={72} />
            </motion.div>
          </StaggerItem>

          <StaggerItem>
            <PageTitle className="welcome-title">MBForge</PageTitle>
          </StaggerItem>

          <StaggerItem>
            <BodyText size="lg" className="welcome-subtitle">
              {t('welcome.subtitle')}
            </BodyText>
          </StaggerItem>

          <StaggerItem>
            <div className="welcome-actions">
              <Button
                variant="primary"
                size="lg"
                onClick={() => setPage('create')}
                icon={<FolderIcon size={16} />}
              >
                {t('welcome.createProject')}
              </Button>
              <Button
                variant="secondary"
                size="lg"
                onClick={() => setPage('open')}
                icon={<FolderIcon size={16} />}
              >
                {t('welcome.openProject')}
              </Button>
            </div>
          </StaggerItem>

          {recentProjects.length > 0 && (
            <StaggerItem>
              <div className="welcome-recent">
                <div className="welcome-recent-header">
                  <SectionTitle>{t('welcome.recentProjects')}</SectionTitle>
                  <IconButton
                    size={32}
                    active={editing}
                    title={editing ? t('common.close') : t('common.copy')}
                    onClick={() => { setEditing(!editing); setDeleting(null) }}
                  >
                    <TrashIcon size={16} />
                  </IconButton>
                </div>
                <StaggerContainer stagger={0.04}>
                  <div className="welcome-recent-list">
                    {recentProjects.map((p) => (
                      <StaggerItem key={p.path}>
                        <motion.div
                          className={`welcome-recent-item ${deleting === p.path ? 'welcome-recent-item--deleting' : ''}`}
                          whileHover={projectCardHover}
                        >
                          {editing && (
                            <motion.button
                              onClick={() => {
                                setDeleting(p.path)
                                setTimeout(() => {
                                  const updated = removeRecentFromStorage(p.path)
                                  setRecentProjects(updated)
                                  setDeleting(null)
                                  if (updated.length === 0) setEditing(false)
                                }, 300)
                              }}
                              whileTap={tapScale}
                              className="welcome-recent-delete-btn"
                            >
                              <XIcon size={14} />
                            </motion.button>
                          )}
                          <button
                            onClick={() => openByName(p.path)}
                            disabled={loading || deleting === p.path}
                            className="welcome-recent-item-btn"
                          >
                            <Caption truncate className="welcome-recent-name">
                              {p.name}
                            </Caption>
                            <Caption truncate className="welcome-recent-path">
                              {p.path}
                            </Caption>
                          </button>
                        </motion.div>
                      </StaggerItem>
                    ))}
                  </div>
                </StaggerContainer>
              </div>
            </StaggerItem>
          )}
        </StaggerContainer>
      </div>
    </motion.div>
  )
}
