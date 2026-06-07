import { useState } from 'react'
import { motion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { openProject } from '../api/tauri-bridge'
import { FolderIcon, ArrowLeftIcon, MoleculeLogo, TrashIcon, XIcon } from './icons'
import { StaggerContainer, StaggerItem } from './animations/StaggerContainer'
import { showToast } from '../hooks/useToast'
import { cleanWindowsPath } from '../utils/path'
import {
  fadeIn,
  slideFromRight,
  logoEntrance,
  projectCardHover,
  tapScale,
} from '../hooks/useAnimations'
import Button from '../components/ui/Button'
import IconButton from '../components/ui/IconButton'
import Input from '../components/ui/Input'
import PageTitle from '../components/ui/PageTitle'
import SectionTitle from '../components/ui/SectionTitle'
import BodyText from '../components/ui/BodyText'
import Caption from '../components/ui/Caption'
import Spinner from '../components/ui/Spinner'
import { FolderPicker } from '../components/ui/FolderPicker'

interface RecentProject {
  name: string
  path: string
}

const RECENT_KEY = 'mbforge_recent_projects'
const MAX_RECENT = 20

function loadRecent(): RecentProject[] {
  try {
    const raw: RecentProject[] = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
    return raw.map(r => ({ ...r, path: cleanWindowsPath(r.path) }))
  } catch {
    return []
  }
}

function persistRecent(path: string, name: string) {
  const cleaned = cleanWindowsPath(path)
  const list = loadRecent()
  const filtered = list.filter(p => p.path !== cleaned)
  const next = [
    { name: name || cleaned.split(/[/\\]/).pop() || cleaned, path: cleaned },
    ...filtered,
  ].slice(0, MAX_RECENT)
  localStorage.setItem(RECENT_KEY, JSON.stringify(next))
}

function removeRecentFromStorage(path: string) {
  const list = loadRecent().filter(p => p.path !== path)
  localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  return list
}

/** 去掉路径首尾的引号 */
function sanitizePath(p: string): string {
  return p.replace(/^["']+|["']+$/g, '').trim()
}

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
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>(loadRecent)

  const handleProjectSuccess = (root: string, name: string) => {
    localStorage.setItem('mbforge_project_root', root)
    persistRecent(root, name)
    onProjectOpened?.(root)
  }

  const openByName = async (path: string) => {
    setLoading(true)
    try {
      const resp = await openProject(path)
      if (resp.success && resp.project) {
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
      if (resp.success && resp.project) {
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
      if (resp.success && resp.project) {
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

  // ---- 创建项目二级页 ----
  if (page === 'create') {
    return (
      <motion.div
        variants={slideFromRight}
        initial="hidden"
        animate="visible"
        exit="exit"
        style={{ flex: 1, padding: '32px', overflow: 'auto', display: 'flex', flexDirection: 'column' }}
      >
        <div style={{ maxWidth: '500px', margin: '60px auto 0', width: '100%' }}>
          <div style={{ marginBottom: '24px' }}>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setPage('home'); setSelectedDir(''); setProjectName('') }}
            >
              <ArrowLeftIcon size={16} /> {t('common.cancel')}
            </Button>
          </div>

          <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '24px' }}>{t('welcome.createProject')}</h2>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              {t('welcome.selectFolder')}
            </label>
            <FolderPicker
              value={selectedDir}
              onChange={(path) => setSelectedDir(sanitizePath(path))}
              placeholder={t('welcome.selectFolder')}
              title={t('welcome.selectFolder')}
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              {t('welcome.projectName')}
            </label>
            <Input
              value={projectName}
              onChange={e => setProjectName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder={t('welcome.projectNamePlaceholder')}
              autoFocus
            />
          </div>

          {selectedDir && projectName && (
            <div style={{ marginBottom: '16px', padding: '10px 14px', background: 'var(--bg-surface)', borderRadius: '8px' }}>
              <Caption>{t('welcome.create')}: <strong>{selectedDir}/{projectName}</strong></Caption>
            </div>
          )}

          <Button
            variant="primary"
            size="lg"
            disabled={loading || !selectedDir.trim() || !projectName.trim()}
            onClick={handleCreate}
          >
            {loading ? (
              <>
                <Spinner size={14} color="currentColor" />
                {t('common.loading')}
              </>
            ) : t('welcome.create')}
          </Button>
        </div>
      </motion.div>
    )
  }

  // ---- 打开项目二级页 ----
  if (page === 'open') {
    return (
      <motion.div
        variants={slideFromRight}
        initial="hidden"
        animate="visible"
        exit="exit"
        style={{ flex: 1, padding: '32px', overflow: 'auto', display: 'flex', flexDirection: 'column' }}
      >
        <div style={{ maxWidth: '500px', margin: '60px auto 0', width: '100%' }}>
          <div style={{ marginBottom: '24px' }}>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setPage('home'); setSelectedDir('') }}
            >
              <ArrowLeftIcon size={16} /> {t('common.cancel')}
            </Button>
          </div>

          <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '24px' }}>{t('welcome.openProject')}</h2>

          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              {t('common.project')}
            </label>
            <FolderPicker
              value={selectedDir}
              onChange={(path) => {
                setSelectedDir(sanitizePath(path))
              }}
              placeholder={t('welcome.selectFolder')}
              title={t('welcome.openProject')}
            />
          </div>

          <Button
            variant="primary"
            size="lg"
            disabled={loading || !selectedDir.trim()}
            onClick={handleOpenDir}
          >
            {loading ? (
              <>
                <Spinner size={14} color="currentColor" />
                {t('common.loading')}
              </>
            ) : t('welcome.openProject')}
          </Button>
        </div>
      </motion.div>
    )
  }

  // ---- 首页 ----
  return (
    <motion.div
      variants={fadeIn}
      initial="hidden"
      animate="visible"
      style={{ flex: 1, padding: '32px', overflow: 'auto', display: 'flex', flexDirection: 'column' }}
    >
      <div style={{ maxWidth: '600px', margin: '60px auto 0', textAlign: 'center', width: '100%' }}>
        <StaggerContainer stagger={0.08}>
          {/* Logo */}
          <StaggerItem>
            <motion.div
              variants={logoEntrance}
              initial="hidden"
              animate="visible"
              style={{ margin: '0 auto 28px' }}
            >
              <MoleculeLogo size={72} />
            </motion.div>
          </StaggerItem>

          <StaggerItem>
            <PageTitle style={{ fontSize: '32px', fontWeight: 700, letterSpacing: '-1px', marginBottom: '12px' }}>
              MBForge
            </PageTitle>
          </StaggerItem>

          <StaggerItem>
            <BodyText size="lg" style={{ marginBottom: '40px' }}>
              {t('welcome.subtitle')}
            </BodyText>
          </StaggerItem>

          {/* 操作按钮 */}
          <StaggerItem>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', marginBottom: '32px' }}>
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

          {/* OCR Provider 信息 */}
          {recentProjects.length > 0 && (
            <StaggerItem>
              <div style={{ textAlign: 'left', marginTop: '8px' }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '12px',
                }}>
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
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    {recentProjects.map((p) => (
                      <StaggerItem key={p.path}>
                        <motion.div
                          style={{
                            display: 'flex', alignItems: 'center',
                            padding: '12px 16px', background: 'var(--bg-surface)',
                            border: '1px solid var(--border)', borderRadius: '10px',
                            width: '100%', boxSizing: 'border-box',
                            borderColor: deleting === p.path ? '#e74c3c' : undefined,
                            opacity: deleting === p.path ? 0.5 : 1,
                          }}
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
                              style={{
                                background: 'none', border: 'none', cursor: 'pointer', padding: '2px 8px 2px 0',
                                color: '#e74c3c', flexShrink: 0,
                              }}
                            >
                              <XIcon size={14} />
                            </motion.button>
                          )}
                          <button
                            onClick={() => openByName(p.path)}
                            disabled={loading || deleting === p.path}
                            style={{
                              flex: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                              background: 'none', border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
                              textAlign: 'left', padding: 0, opacity: loading ? 0.6 : 1,
                            }}
                          >
                            <Caption truncate color="var(--text-primary)" style={{ fontSize: '14px', fontWeight: 500, marginRight: '16px' }}>
                              {p.name}
                            </Caption>
                            <Caption truncate style={{ flexShrink: 0 }}>
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
