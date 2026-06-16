/** Right-side help popover, anchored under the Header's help button.
 *
 * Self-contained: manages its own open state via a ref + click-outside,
 * renders nothing when closed. Content is the canonical project
 * folder layout (formerly displayed on the home page). */

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FOLDER_SPECS, PAPERS_DIR, NOTES_DIR } from '../config/folderLayout'

interface Props {
  /** Element the popover anchors to (typically the help button). */
  anchorRef: React.RefObject<HTMLElement | null>
  /** Called when the popover requests close (click outside, Esc). */
  onClose: () => void
}

export default function HelpPopover({ anchorRef, onClose }: Props) {
  const { t } = useTranslation()
  const panelRef = useRef<HTMLDivElement | null>(null)
  const [pos, setPos] = useState<{ top: number; right: number } | null>(null)

  // Position the popover just below the anchor on mount + on resize/scroll.
  useEffect(() => {
    const place = () => {
      const a = anchorRef.current
      if (!a) return
      const r = a.getBoundingClientRect()
      setPos({ top: r.bottom + 6, right: window.innerWidth - r.right })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [anchorRef])

  // Click outside + Esc to close.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node | null
      if (!t) return
      if (panelRef.current?.contains(t)) return
      if (anchorRef.current?.contains(t)) return
      onClose()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [anchorRef, onClose])

  if (!pos) return null

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-label={t('help.folderRules')}
      style={{
        position: 'fixed',
        top: pos.top,
        right: pos.right,
        zIndex: 1100,
        width: 'min(440px, calc(100vw - 24px))',
        maxHeight: '70vh',
        overflowY: 'auto',
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        boxShadow: '0 12px 40px rgba(0,0,0,0.35)',
        padding: '14px 16px',
        fontSize: '12px',
        color: 'var(--text-primary)',
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: '10px' }}>{t('help.folderRules')}</div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '8px 14px',
          marginBottom: '10px',
        }}
      >
        {FOLDER_SPECS.map((spec) => {
          const roleColor =
            spec.role === 'input'
              ? 'rgba(34,197,94,0.18)'
              : spec.role === 'output'
                ? 'rgba(59,130,246,0.18)'
                : 'rgba(148,163,184,0.18)'
          return (
            <div
              key={spec.name}
              style={{
                padding: '8px 10px',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                display: 'flex',
                flexDirection: 'column',
                gap: 2,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span
                  style={{
                    padding: '0 5px',
                    borderRadius: 3,
                    fontSize: 9,
                    fontWeight: 600,
                    background: roleColor,
                  }}
                >
                  {spec.role === 'input' ? 'IN' : spec.role === 'output' ? 'OUT' : 'META'}
                </span>
                <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{spec.name}/</span>
              </div>
              <span style={{ color: 'var(--text-muted)' }}>{spec.accepts}</span>
              <span style={{ color: 'var(--text-muted)' }}>{spec.description}</span>
            </div>
          )
        })}
      </div>
      <div
        style={{
          padding: '8px 10px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: '6px',
          color: 'var(--text-muted)',
        }}
      >
        {t('help.folderCreationHint')}
        <br />
        {t('help.folderInstruction', { papers: PAPERS_DIR, notes: NOTES_DIR })}
      </div>
    </div>
  )
}
