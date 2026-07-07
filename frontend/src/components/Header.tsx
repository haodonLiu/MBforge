import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { HelpIcon } from './icons'
import IconButton from './ui/IconButton'
import HelpPopover from './HelpPopover'

interface HeaderProps {
  gridColumn: string
  currentPage: string
}

export default function Header({ gridColumn, currentPage }: HeaderProps) {
  const { t } = useTranslation()
  const [helpOpen, setHelpOpen] = useState(false)
  const helpBtnRef = useRef<HTMLButtonElement | null>(null)
  const pageTitle: Record<string, string> = {
    workspace: t('nav.workspace'),
    discover: t('nav.discover'),
    molecules: t('nav.molecules'),
    queue: t('nav.queue'),
    notes: t('nav.notes'),
    settings: t('nav.settings'),
  }

  const title = pageTitle[currentPage] || 'MBForge'

  return (
    <header style={{
      gridColumn,
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
        gap: '12px',
        fontSize: '15px',
        fontWeight: 600,
        color: 'var(--text-primary)',
      }}>
        {title}
      </div>
      <div style={{
        flex: 1,
        display: 'flex',
        justifyContent: 'center',
        padding: '0 24px',
      }}>
        <input
          type="text"
          placeholder={t('discover.search.placeholder')}
          style={{
            width: '100%',
            maxWidth: '480px',
            height: '32px',
            padding: '0 12px',
            borderRadius: '8px',
            border: '1px solid var(--border)',
            background: 'var(--bg-surface)',
            color: 'var(--text-primary)',
            fontSize: '13px',
            outline: 'none',
          }}
          onFocus={(e) => {
            e.target.style.borderColor = 'var(--accent)'
          }}
          onBlur={(e) => {
            e.target.style.borderColor = 'var(--border)'
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && e.currentTarget.value.trim()) {
              window.location.href = `/discover?q=${encodeURIComponent(e.currentTarget.value.trim())}`
            }
          }}
        />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <span ref={helpBtnRef} style={{ display: 'inline-flex' }}>
          <IconButton
            title={t('header.projectFolderRules')}
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
