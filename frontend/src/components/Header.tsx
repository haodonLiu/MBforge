import { useRef, useState } from 'react'
import { HelpIcon } from './icons'
import IconButton from './ui/IconButton'
import HelpPopover from './HelpPopover'

export default function Header() {
  const [helpOpen, setHelpOpen] = useState(false)
  const helpBtnRef = useRef<HTMLButtonElement | null>(null)

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
        <span ref={helpBtnRef} style={{ display: 'inline-flex' }}>
          <IconButton
            title="项目目录规范"
            onClick={() => setHelpOpen((v) => !v)}
            active={helpOpen}
          >
            <HelpIcon size={18} />
          </IconButton>
        </span>
      </div>
      {helpOpen && (
        <HelpPopover anchorRef={helpBtnRef} onClose={() => setHelpOpen(false)} />
      )}
    </header>
  )
}
