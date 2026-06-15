// LLM env status card — read-only display of the LLM config + link status.
//
// The LLM is configured exclusively via MBFORGE_LLM_* env vars (see
// src-tauri/src/core/agent/rig_adapter.rs). This component fetches the
// current values via getLlmEnvConfig, then offers a "Test Connection"
// button that runs a minimal probe via testLlmConnection. The Settings
// UI cannot override the env values — the env is the source of truth.

import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getLlmEnvConfig, testLlmConnection, type LlmEnvStatus, type LlmLinkStatus } from '../../api/tauri/agent'
import { PROVIDER_META } from './modelConfigs'

const STATUS_LABEL: Record<LlmLinkStatus, { text: string; tone: 'ok' | 'warn' | 'error' | 'idle' }> = {
  not_configured: { text: 'Not configured', tone: 'warn' },
  ok: { text: 'Online', tone: 'ok' },
  unreachable: { text: 'Unreachable', tone: 'error' },
  http_error: { text: 'HTTP error', tone: 'error' },
  auth_error: { text: 'Auth failed', tone: 'error' },
}

const STATUS_COLOR: Record<'ok' | 'warn' | 'error' | 'idle', string> = {
  ok: '#10b981',
  warn: '#f59e0b',
  error: '#ef4444',
  idle: '#6b7280',
}

export default function LlmStatusCard() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<LlmEnvStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const s = await getLlmEnvConfig()
      setStatus(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  const probe = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const s = await testLlmConnection()
      setStatus(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  // Fetch env config on mount; user can hit "Test Connection" to probe.
  useEffect(() => {
    void refresh()
  }, [refresh])

  if (!status) {
    return (
      <div style={{ padding: 12, color: STATUS_COLOR.idle }}>
        {error ? `Error: ${error}` : t('settings.llmLoading')}
      </div>
    )
  }

  const label = STATUS_LABEL[status.status]
  const providerLabel = (PROVIDER_META[status.provider] ?? { label: status.provider }).label

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        padding: 14,
        border: '1px solid var(--border-color, #2a2a2a)',
        borderRadius: 8,
        background: 'var(--bg-secondary, rgba(255,255,255,0.02))',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          aria-label={label.text}
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: STATUS_COLOR[label.tone],
            boxShadow: `0 0 6px ${STATUS_COLOR[label.tone]}`,
          }}
        />
        <strong style={{ color: STATUS_COLOR[label.tone] }}>{label.text}</strong>
        {status.latency_ms != null && (
          <span style={{ color: '#888', fontSize: 12 }}>({status.latency_ms} ms)</span>
        )}
      </div>

      <Field label={t('settings.llmProvider')}>{providerLabel}</Field>
      <Field label={t('settings.llmBaseUrl')}>
        <code style={{ fontSize: 12 }}>{status.base_url || '—'}</code>
      </Field>
      <Field label={t('settings.llmModel')}>
        <code style={{ fontSize: 12 }}>{status.model || '—'}</code>
      </Field>
      <Field label={t('settings.llmApiKey')}>
        {status.api_key_set ? (
          <span style={{ color: STATUS_COLOR.ok }}>{t('settings.llmApiKeySet')}</span>
        ) : (
          <span style={{ color: STATUS_COLOR.warn }}>{t('settings.llmApiKeyMissing')}</span>
        )}
      </Field>

      {status.error && (
        <div
          style={{
            marginTop: 4,
            padding: 8,
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 4,
            color: STATUS_COLOR.error,
            fontSize: 12,
            fontFamily: 'monospace',
            wordBreak: 'break-all',
          }}
        >
          {status.error}
        </div>
      )}

      {error && (
        <div style={{ color: STATUS_COLOR.error, fontSize: 12 }}>{error}</div>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        <button
          type="button"
          onClick={probe}
          disabled={loading}
          style={{
            padding: '6px 12px',
            border: '1px solid var(--border-color, #444)',
            borderRadius: 4,
            background: 'transparent',
            color: 'inherit',
            cursor: loading ? 'wait' : 'pointer',
          }}
        >
          {loading ? t('settings.llmTesting') : t('settings.llmTestConnection')}
        </button>
        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          style={{
            padding: '6px 12px',
            border: '1px solid transparent',
            borderRadius: 4,
            background: 'transparent',
            color: '#888',
            cursor: loading ? 'wait' : 'pointer',
          }}
        >
          {t('settings.llmRefresh')}
        </button>
      </div>

      <p style={{ margin: 0, fontSize: 11, color: '#888' }}>
        {t('settings.llmEnvReadonly')}
      </p>
    </div>
  )
}

interface FieldProps {
  label: string
  children: React.ReactNode
}

function Field({ label, children }: FieldProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 13 }}>
      <span style={{ minWidth: 90, color: '#888' }}>{label}</span>
      <span style={{ flex: 1 }}>{children}</span>
    </div>
  )
}
