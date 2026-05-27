import { useNavigate } from 'react-router-dom'
import { FlaskIcon, SearchIcon, ChatIcon, WorkflowIcon, PlusIcon, FileTextIcon, LayoutIcon, SettingsIcon } from './icons'

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
        <button
          title="文件树"
          onClick={onToggleFileTree}
          style={{
            width: '44px',
            height: '44px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '8px',
            border: 'none',
            cursor: 'pointer',
            transition: 'all 0.15s',
            background: fileTreeOpen ? 'var(--accent-muted)' : 'transparent',
            color: fileTreeOpen ? 'var(--accent)' : 'var(--text-secondary)',
          }}
          onMouseEnter={e => {
            if (!fileTreeOpen) {
              e.currentTarget.style.background = 'var(--bg-hover)'
              e.currentTarget.style.color = 'var(--text-primary)'
            }
          }}
          onMouseLeave={e => {
            if (!fileTreeOpen) {
              e.currentTarget.style.background = 'transparent'
              e.currentTarget.style.color = 'var(--text-secondary)'
            }
          }}
        >
          <FileTextIcon size={20} />
        </button>

        {NAV_ITEMS.map(item => {
          const Icon = item.icon
          const isActive = current === item.id
          return (
            <button
              key={item.id}
              title={item.label}
              onClick={() => handleClick(item)}
              style={{
                width: '44px',
                height: '44px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: '8px',
                border: 'none',
                cursor: 'pointer',
                transition: 'all 0.15s',
                background: isActive ? 'var(--accent-muted)' : 'transparent',
                color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
              }}
              onMouseEnter={e => {
                if (!isActive) {
                  e.currentTarget.style.background = 'var(--bg-hover)'
                  e.currentTarget.style.color = 'var(--text-primary)'
                }
              }}
              onMouseLeave={e => {
                if (!isActive) {
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.color = 'var(--text-secondary)'
                }
              }}
            >
              <Icon size={20} />
            </button>
          )
        })}
      </div>

      <div style={{
        marginTop: 'auto',
        padding: '8px 6px',
        borderTop: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        gap: '2px',
      }}>
        <button
          title="切换项目"
          onClick={onSwitchProject}
          style={{
            width: '44px',
            height: '44px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '8px',
            border: 'none',
            cursor: 'pointer',
            transition: 'all 0.15s',
            background: 'transparent',
            color: 'var(--text-secondary)',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = 'var(--bg-hover)'
            e.currentTarget.style.color = 'var(--text-primary)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = 'transparent'
            e.currentTarget.style.color = 'var(--text-secondary)'
          }}
        >
          <PlusIcon size={20} />
        </button>
        <button
          title="设置"
          onClick={onSettingsOpen}
          style={{
            width: '44px',
            height: '44px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '8px',
            border: 'none',
            cursor: 'pointer',
            transition: 'all 0.15s',
            background: 'transparent',
            color: 'var(--text-secondary)',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = 'var(--bg-hover)'
            e.currentTarget.style.color = 'var(--text-primary)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = 'transparent'
            e.currentTarget.style.color = 'var(--text-secondary)'
          }}
        >
          <SettingsIcon size={20} />
        </button>
      </div>
    </aside>
  )
}
