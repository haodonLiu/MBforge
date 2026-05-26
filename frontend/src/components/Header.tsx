import { HelpIcon } from './icons'

export default function Header() {
  return (
    <header style={{
      gridColumn: '2',
      gridRow: '1',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      height: '48px',
      padding: '0 24px',
      background: 'var(--bg-base)',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        fontSize: '15px',
        fontWeight: 600,
        color: 'var(--text-primary)',
      }}>
        MBForge
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <button
          title="帮助"
          className="icon-btn"
          onClick={() => alert('帮助文档即将推出')}
        >
          <HelpIcon size={18} />
        </button>
      </div>
    </header>
  )
}
