import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { FlaskIcon, SearchIcon, ChatIcon, WorkflowIcon, PlusIcon, FileTextIcon, LayoutIcon, SettingsIcon } from './icons'
import IconButton from '../components/ui/IconButton'

interface Props {
  current: string
  onNavigate: (page: string) => void
  onSettingsOpen: () => void
  onSwitchProject: () => void
  fileTreeOpen: boolean
  onToggleFileTree: () => void
}

const NAV_ITEMS = [
  { id: 'project', label: '项目看板', path: '/project', icon: LayoutIcon },
  { id: 'search', label: '搜索', path: '/search', icon: SearchIcon },
  { id: 'chat', label: '对话', path: '/chat', icon: ChatIcon },
  { id: 'molecules', label: '分子库', path: '/molecules', icon: FlaskIcon },
  { id: 'workflow', label: '工作流', path: '/workflow', icon: WorkflowIcon },
]

function Tooltip({ text, children }: { text: string; children: React.ReactNode }) {
  const [show, setShow] = useState(false)
  return (
    <div
      style={{ position: 'relative' }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && (
        <motion.div
          initial={{ opacity: 0, x: -4 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          style={{
            position: 'absolute',
            left: 'calc(100% + 8px)',
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'var(--accent)',
            color: '#fff',
            padding: '4px 10px',
            borderRadius: '6px',
            fontSize: '12px',
            fontWeight: 500,
            whiteSpace: 'nowrap',
            pointerEvents: 'none',
            zIndex: 100,
          }}
        >
          {text}
        </motion.div>
      )}
    </div>
  )
}

function NavButton({
  active,
  onClick,
  label,
  icon: Icon,
}: {
  active: boolean
  onClick: () => void
  label: string
  icon: React.FC<{ size?: number }>
}) {
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

export default function Sidebar({ current, onNavigate, onSettingsOpen, onSwitchProject, fileTreeOpen, onToggleFileTree }: Props) {
  const navigate = useNavigate()

  const handleClick = (item: typeof NAV_ITEMS[0]) => {
    onNavigate(item.id)
    navigate(item.path)
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
        {/* File tree toggle at top */}
        <Tooltip text="文件树">
          <IconButton active={fileTreeOpen} onClick={onToggleFileTree}>
            <FileTextIcon size={20} />
          </IconButton>
        </Tooltip>

        {NAV_ITEMS.map((item) => (
          <NavButton
            key={item.id}
            active={current === item.id}
            onClick={() => handleClick(item)}
            label={item.label}
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
        <Tooltip text="切换项目">
          <IconButton onClick={onSwitchProject}>
            <PlusIcon size={20} />
          </IconButton>
        </Tooltip>
        <Tooltip text="设置">
          <IconButton onClick={onSettingsOpen}>
            <SettingsIcon size={20} />
          </IconButton>
        </Tooltip>
      </div>
    </aside>
  )
}
