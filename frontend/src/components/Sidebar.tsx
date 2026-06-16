import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { FlaskIcon, SearchIcon, PlusIcon, FileTextIcon, LayoutIcon, SettingsIcon, NoteIcon, QueueIcon } from './icons'
import IconButton from '@/components/ui/IconButton'
import Tooltip from '@/components/ui/Tooltip'

interface Props {
  current: string
  onNavigate: (page: string) => void
  onSwitchProject: () => void
  projectScopeOpen: boolean
  onToggleProjectScope: () => void
}

const PRIMARY_ITEMS = [
  { id: 'workspace', path: '/workspace', icon: LayoutIcon, labelKey: 'nav.workspace' },
  { id: 'discover', path: '/discover', icon: SearchIcon, labelKey: 'nav.discover' },
  { id: 'molecules', path: '/molecules', icon: FlaskIcon, labelKey: 'nav.molecules' },
]

const SECONDARY_ITEMS = [
  { id: 'queue', path: '/queue', icon: QueueIcon, labelKey: 'nav.queue' },
  { id: 'notes', path: '/notes', icon: NoteIcon, labelKey: 'nav.notes' },
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

export default function Sidebar({ current, onNavigate, onSwitchProject, projectScopeOpen, onToggleProjectScope }: Props) {
  const navigate = useNavigate()
  const { t } = useTranslation()

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
      </div>

      <div style={{
        marginTop: 'auto',
        padding: '8px 6px',
        borderTop: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        gap: '2px',
      }}>
        <Tooltip text={t('nav.settings')}>
          <IconButton onClick={() => { onNavigate('settings'); void navigate('/settings') }}>
            <SettingsIcon size={20} />
          </IconButton>
        </Tooltip>
        <Tooltip text={t('nav.switchProject')}>
          <IconButton onClick={onSwitchProject}>
            <PlusIcon size={20} />
          </IconButton>
        </Tooltip>
      </div>
    </aside>
  )
}