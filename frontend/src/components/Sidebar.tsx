import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { FlaskIcon, SearchIcon, PlusIcon, FileTextIcon, LayoutIcon, SettingsIcon, BarChartIcon, NoteIcon, QueueIcon } from './icons'
import IconButton from '@/components/ui/IconButton'
import Tooltip from '@/components/ui/Tooltip'
import ModelStatusButton from './ModelStatusButton'
import { useAppContext } from '@/context/AppContext'
import { ingestStats } from '@/api/tauri/ingest_queue'
import { EVT } from '@/api/tauri-events'
import { listen } from '@tauri-apps/api/event'

interface Props {
  current: string
  onNavigate: (page: string) => void
  onSwitchProject: () => void
  projectScopeOpen: boolean
  onToggleProjectScope: () => void
  queuePanelOpen: boolean
  onToggleQueuePanel: () => void
}

const PRIMARY_ITEMS = [
  { id: 'workspace', path: '/workspace', icon: LayoutIcon, labelKey: 'nav.workspace' },
  { id: 'discover', path: '/discover', icon: SearchIcon, labelKey: 'nav.discover' },
  { id: 'molecules', path: '/molecules', icon: FlaskIcon, labelKey: 'nav.molecules' },
  { id: 'analysis', path: '/analysis', icon: BarChartIcon, labelKey: 'nav.analysis' },
]

const SECONDARY_ITEMS = [
  { id: 'queue', path: '/queue', icon: QueueIcon, labelKey: 'nav.queue' },
  { id: 'notes', path: '/notes', icon: NoteIcon, labelKey: 'nav.notes' },
]

const UTILITY_ITEMS = [
  { id: 'settings', path: '/settings', icon: SettingsIcon, labelKey: 'nav.settings' },
]

interface NavButtonProps {
  active: boolean
  onClick: () => void
  label: string
  icon: React.FC<{ size?: number }>
}

function NavButton({
  active,
  onClick,
  label,
  icon: Icon,
}: NavButtonProps) {
  return (
    <Tooltip text={label}>
      <div style={{ position: 'relative' }}>
        {active && (
          <motion.div
            layoutId="sidebar-indicator"
            style={{
              position: 'absolute',
              left: 0,
              top: '50%',
              transform: 'translateY(-50%)',
              width: '3px',
              height: '20px',
              background: 'var(--accent)',
              borderRadius: '0 2px 2px 0',
            }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          />
        )}
        <IconButton active={active} onClick={onClick}>
          <Icon size={20} />
        </IconButton>
      </div>
    </Tooltip>
  )
}

export default function Sidebar({ current, onNavigate, onSwitchProject, projectScopeOpen, onToggleProjectScope, queuePanelOpen, onToggleQueuePanel }: Props) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { projectRoot } = useAppContext()
  const [queueCount, setQueueCount] = useState(0)

  useEffect(() => {
    if (!projectRoot) {
      setQueueCount(0)
      return
    }
    const load = async () => {
      try {
        const stats = await ingestStats(projectRoot)
        setQueueCount(stats.pending + stats.processing + stats.failed)
      } catch (e) {
        console.error('[Sidebar] stats failed:', e)
      }
    }
    void load()

    let unlisten: (() => void) | null = null
    const setup = async () => {
      unlisten = await listen(EVT.IngestQueueUpdate, () => {
        void load()
      })
    }
    void setup().catch((e: unknown) => {
      console.error('[Sidebar] listen failed:', e)
    })

    return () => {
      unlisten?.()
    }
  }, [projectRoot])

  const handleClick = (item: typeof PRIMARY_ITEMS[0]) => {
    onNavigate(item.id)
    void navigate(item.path)
  }

  return (
    <aside style={{
      gridColumn: '1',
      gridRow: '1 / 4',
      background: 'var(--bg-surface)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      <div style={{ padding: '8px 6px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
        {/* ProjectScope toggle at top */}
        <Tooltip text={t('nav.projectScope')}>
          <IconButton active={projectScopeOpen} onClick={onToggleProjectScope}>
            <FileTextIcon size={20} />
          </IconButton>
        </Tooltip>

        {PRIMARY_ITEMS.map((item) => (
          <NavButton
            key={item.id}
            active={current === item.id}
            onClick={() => handleClick(item)}
            label={t(item.labelKey)}
            icon={item.icon}
          />
        ))}

        {/* Queue mini-panel toggle */}
        <Tooltip text={t('sidebarQueue.title')}>
          <div
            style={{ position: 'relative' }}
            onContextMenu={(e: React.MouseEvent<HTMLDivElement>) => {
              e.preventDefault()
              onToggleQueuePanel()
            }}
          >
            <IconButton active={queuePanelOpen} onClick={onToggleQueuePanel}>
              <QueueIcon size={20} />
            </IconButton>
            {queueCount > 0 && (
              <span style={{
                position: 'absolute',
                top: '4px',
                right: '4px',
                minWidth: '16px',
                height: '16px',
                padding: '0 4px',
                borderRadius: '8px',
                background: 'var(--bad)',
                color: 'white',
                fontSize: '10px',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 0 2px var(--bg-surface)',
              }}>
                {queueCount > 99 ? '99+' : queueCount}
              </span>
            )}
          </div>
        </Tooltip>

        <div style={{ margin: '8px 6px', borderTop: '1px solid var(--border)' }} />

        {SECONDARY_ITEMS.map((item) => (
          <NavButton
            key={item.id}
            active={current === item.id}
            onClick={() => handleClick(item)}
            label={t(item.labelKey)}
            icon={item.icon}
          />
        ))}

        {UTILITY_ITEMS.map((item) => (
          <NavButton
            key={item.id}
            active={current === item.id}
            onClick={() => handleClick(item)}
            label={t(item.labelKey)}
            icon={item.icon}
          />
        ))}
      </div>

      <div style={{
        marginTop: 'auto',
        padding: '8px 6px',
        borderTop: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        gap: '2px',
      }}>
        <ModelStatusButton projectRoot={projectRoot} />
        <Tooltip text={t('nav.switchProject')}>
          <IconButton onClick={onSwitchProject}>
            <PlusIcon size={20} />
          </IconButton>
        </Tooltip>
      </div>
    </aside>
  )
}
