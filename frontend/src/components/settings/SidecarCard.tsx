/** Sidecar (Python model server) health probe + manual restart.
 * Used by Settings > System tab. */

import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { sidecarStatus, sidecarRestart, type SidecarStatus } from '../../api/http/sidecar'
import { showToast } from '../../hooks/useToast'
import Button from '@/components/ui/Button'
import Caption from '@/components/ui/Caption'

function formatUptime(secs: number): string {
  if (secs < 60) return `${secs} s`
  if (secs < 3600) return `${Math.floor(secs / 60)} min`
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  return `${h} h ${m} min`
}

export default function SidecarCard() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<SidecarStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [restarting, setRestarting] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const s = await sidecarStatus()
      setStatus(s)
    } catch (e) {
      console.warn('[SidecarCard] status failed:', e)
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const handleRestart = async () => {
    setRestarting(true)
    try {
      await sidecarRestart()
      showToast(t('sidecar.restarting'), 'info')
      // 等几秒再读状态（spawn + model prewarm 耗时）
      setTimeout(() => {
        void refresh()
      }, 3000)
    } catch (e) {
      showToast(t('sidecar.restartFailed', { error: e instanceof Error ? e.message : String(e) }), 'error')
    } finally {
      setRestarting(false)
    }
  }

  return (
    <div
      style={{
        padding: '14px 18px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>Python Sidecar</h3>
        <Button variant="secondary" size="sm" onClick={refresh} disabled={loading}>
          {loading ? t('sidecar.refreshing') : t('common.refresh')}
        </Button>
      </div>
      <Caption>
        {t('sidecar.description')}
      </Caption>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: '10px',
        }}
      >
        <Stat
          label={t('sidecar.status')}
          value={status ? (status.healthy ? 'Online' : 'Offline') : '—'}
          tone={status?.healthy === true ? 'ok' : status?.healthy === false ? 'error' : 'idle'}
        />
        <Stat label={t('sidecar.uptime')} value={status ? formatUptime(status.uptimeSecs) : '—'} />
        <Stat label={t('sidecar.restartCount')} value={status ? String(status.restartCount) : '—'} />
        <Stat label={t('sidecar.lastError')} value={status?.lastError ?? '—'} mono />
      </div>
      <div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleRestart}
          loading={restarting}
        >
          {t('sidecar.restart')}
        </Button>
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  tone,
  mono = false,
}: {
  label: string
  value: string
  tone?: 'ok' | 'error' | 'idle'
  mono?: boolean
}) {
  const color =
    tone === 'ok' ? '#10b981' : tone === 'error' ? '#ef4444' : 'var(--text-primary)'
  return (
    <div
      style={{
        padding: '8px 10px',
        background: 'var(--bg-base)',
        border: '1px solid var(--border)',
        borderRadius: '6px',
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      <Caption style={{ fontSize: 11 }}>{label}</Caption>
      <span
        style={{
          fontSize: '14px',
          fontWeight: 600,
          color,
          fontFamily: mono ? 'ui-monospace, monospace' : 'inherit',
          wordBreak: 'break-all',
        }}
      >
        {value}
      </span>
    </div>
  )
}
