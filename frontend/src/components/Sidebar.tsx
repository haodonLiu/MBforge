import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { FlaskIcon, SearchIcon, LayoutIcon, SettingsIcon, NoteIcon, QueueIcon } from './icons'
import Tooltip from '@/components/ui/Tooltip'

interface Props {
  current: string
  onNavigate: (page: string) => void
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

function NavButton({ active, onClick, label, icon: Icon }: NavButtonProps) {
  return (
    <Tooltip text={label}>
      <motion.button
        onClick={onClick}
        whileTap={{ scale: 0.9 }}
        style={{
          width: 40,
          height: 40,
          borderRadius: 10,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: 'none',
          cursor: 'pointer',
          background: active ? 'var(--accent)' : 'transparent',
          color: active ? '#fff' : 'var(--text-secondary)',
          transition: 'background 0.2s, color 0.2s',
        }}
      >
        <Icon size={20} />
      </motion.button>
    </Tooltip>
  )
}

export default function Sidebar({ current, onNavigate }: Props) {
  const navigate = useNavigate()
  const { t } = useTranslation()

  const handleClick = (item: typeof PRIMARY_ITEMS[0]) => {
    onNavigate(item.id)
    navigate(item.path)
  }

  return (
    <aside style={{
      gridColumn: '1',
      gridRow: '1 / 5',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '4px',
      padding: '12px 0',
      background: 'var(--bg-surface)',
      borderRight: '1px solid var(--border)',
      zIndex: 10,
    }}>
      {PRIMARY_ITEMS.map(item => (
        <NavButton
          key={item.id}
          active={current === item.id}
          onClick={() => handleClick(item)}
          label={t(item.labelKey)}
          icon={item.icon}
        />
      ))}

      <div style={{ flex: 1 }} />

      {SECONDARY_ITEMS.map(item => (
        <NavButton
          key={item.id}
          active={current === item.id}
          onClick={() => handleClick(item)}
          label={t(item.labelKey)}
          icon={item.icon}
        />
      ))}

      <div style={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
        <NavButton
          active={current === 'settings'}
          onClick={() => {
            onNavigate('settings')
            navigate('/settings')
          }}
          label={t('nav.settings')}
          icon={SettingsIcon}
        />
      </div>
    </aside>
  )
}
