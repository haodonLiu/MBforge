/**
 * OCR backend configuration modal.
 *
 * Shown when a scanned PDF is detected but no cloud OCR backend is
 * configured. User fills API keys for MinerU / Uniparser / PaddleOCR
 * (all optional; first one wins per the OCR fallback chain), saves
 * via the existing settings store, and the backend picks them up on
 * next document load.
 *
 * Each row links to the provider's API-key acquisition page so the
 * user can get a key without leaving the workflow to search docs.
 *
 * Persistence: keys saved to AppConfig.ocr.{mineru,uniparser,paddleocr}_api_key
 * via `saveSettings`. Backend `AppConfig::load` mirrors them into
 * process env vars so the existing `is_available()` checks pick them up.
 */

import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import Modal from '@/components/ui/Modal'
import Button from '@/components/ui/Button'
import ApiKeyInput from './settings/ApiKeyInput'
import { getSettings, saveSettings } from '@/api/http/settings'
import { openExternalUrl } from '@/api/http/_utils'
import { testOcrMineru, testOcrUniparser, testOcrPaddleocr, testOcrGlmocr, type OcrTestResult } from '@/api/http/text'

type Backend = 'mineru' | 'uniparser' | 'paddleocr-online' | 'paddleocr-local'

interface OcrApiMissingPayload {
  backend: Backend
  doc_id: string
  file_path: string
}

interface FormState {
  mineru_api_key: string
  uniparser_api_key: string
  paddleocr_api_key: string
  paddleocr_host: string
  paddleocr_model: string
  glmocr_api_key: string
}

const EMPTY: FormState = {
  mineru_api_key: '',
  uniparser_api_key: '',
  paddleocr_api_key: '',
  paddleocr_host: '',
  paddleocr_model: '',
  glmocr_api_key: '',
}

const ACQUISITION_URLS: Record<Backend, string> = {
  mineru: 'https://mineru.net/',
  uniparser: 'https://uniparser.dp.tech/',
  'paddleocr-online': 'https://aistudio.baidu.com/paddleocr',
  'paddleocr-local': '',
}

const DISMISS_KEY_PREFIX = 'mbforge.ocr.dismissForever.'
function isDismissedForever(backend: string): boolean {
  try {
    return localStorage.getItem(`${DISMISS_KEY_PREFIX}${backend}`) === '1'
  } catch {
    return false
  }
}

function openExternal(url: string) {
  if (!url) return
  void openExternalUrl(url)
}

export default function OcrConfigModal() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [missingBackend, setMissingBackend] = useState<Backend | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testing, setTesting] = useState<null | 'mineru' | 'uniparser' | 'paddleocr' | 'glmocr'>(null)
  const [testResults, setTestResults] = useState<{
    mineru: OcrTestResult | null
    uniparser: OcrTestResult | null
    paddleocr: OcrTestResult | null
    glmocr: OcrTestResult | null
  }>({ mineru: null, uniparser: null, paddleocr: null, glmocr: null })

  // Listen for the missing-API event from the Rust ingest worker.
  useEffect(() => {
    // No-op: Tauri events not available in web mode
  }, [])

  const close = useCallback(() => setOpen(false), [])

  const dismissForever = useCallback(() => {
    if (missingBackend) {
      try {
        localStorage.setItem(`${DISMISS_KEY_PREFIX}${missingBackend}`, '1')
      } catch {
        // ignore quota errors
      }
    }
    setOpen(false)
  }, [missingBackend])

  const save = useCallback(async () => {
    setSaving(true)
    setError(null)
    try {
      const resp = await saveSettings({
        ocr: {
          provider: 'cloud',
          mineru_api_key: form.mineru_api_key.trim() || null,
          uniparser_api_key: form.uniparser_api_key.trim() || null,
          paddleocr_api_key: form.paddleocr_api_key.trim() || null,
          paddleocr_host: form.paddleocr_host.trim() || null,
          paddleocr_model: form.paddleocr_model.trim() || null,
          glmocr_api_key: form.glmocr_api_key.trim() || null,
        },
      })
      if (!resp.success) {
        setError(resp.error ?? 'unknown error')
        return
      }
      setOpen(false)
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }, [form])

  const fileName = missingBackend
    ? '' // payload removed in event handler above; could pass through if needed
    : ''

  const runTest = async (which: 'mineru' | 'uniparser' | 'paddleocr' | 'glmocr') => {
    setTesting(which)
    try {
      const key =
        which === 'mineru' ? form.mineru_api_key.trim()
        : which === 'uniparser' ? form.uniparser_api_key.trim()
        : which === 'glmocr' ? form.glmocr_api_key.trim()
        : form.paddleocr_api_key.trim()
      const result =
        which === 'mineru' ? await testOcrMineru(null, key)
        : which === 'uniparser' ? await testOcrUniparser(null, key)
        : which === 'glmocr' ? await testOcrGlmocr(key)
        : await testOcrPaddleocr(form.paddleocr_host.trim() || null, key, form.paddleocr_model.trim() || null)
      setTestResults(prev => ({ ...prev, [which]: result }))
    } catch (e) {
      setTestResults(prev => ({
        ...prev,
        [which]: { ok: false, status: null, message: String(e) },
      }))
    } finally {
      setTesting(null)
    }
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title={t('ocr.config.title')}
      width={520}
      maxWidth={520}
      footer={
        <>
          <Button variant="ghost" onClick={dismissForever} disabled={saving}>
            {t('ocr.config.dismissForever')}
          </Button>
          <Button variant="secondary" onClick={close} disabled={saving}>
            {t('common.cancel')}
          </Button>
          <Button variant="primary" onClick={save} loading={saving}>
            {t('common.save')}
          </Button>
        </>
      }
    >
      <p style={{ margin: '0 0 16px', color: 'var(--text-secondary)', fontSize: 13 }}>
        {t('ocr.config.description')}
      </p>

      {error && (
        <div style={{ color: '#dc2626', fontSize: 12, marginBottom: 12 }}>
          {error}
        </div>
      )}

      <BackendRow
        label={t('ocr.config.mineru')}
        placeholder="eyJ0eXBlIjoiSldU..."
        value={form.mineru_api_key}
        onChange={v => setForm(s => ({ ...s, mineru_api_key: v }))}
        onGetKey={() => openExternal(ACQUISITION_URLS.mineru)}
        getKeyLabel={t('ocr.config.getKey')}
        onTest={() => runTest('mineru')}
        testing={testing === 'mineru'}
        testResult={testResults.mineru}
      />

      <BackendRow
        label={t('ocr.config.uniparser')}
        placeholder="up_..."
        value={form.uniparser_api_key}
        onChange={v => setForm(s => ({ ...s, uniparser_api_key: v }))}
        onGetKey={() => openExternal(ACQUISITION_URLS.uniparser)}
        getKeyLabel={t('ocr.config.getKey')}
        onTest={() => runTest('uniparser')}
        testing={testing === 'uniparser'}
        testResult={testResults.uniparser}
      />

      <BackendRow
        label={t('ocr.config.paddleocr')}
        placeholder="bearer token"
        value={form.paddleocr_api_key}
        onChange={v => setForm(s => ({ ...s, paddleocr_api_key: v }))}
        onGetKey={() => openExternal(ACQUISITION_URLS['paddleocr-online'])}
        getKeyLabel={t('ocr.config.getKey')}
        onTest={() => runTest('paddleocr')}
        testing={testing === 'paddleocr'}
        testResult={testResults.paddleocr}
        extra={[
          {
            label: t('ocr.config.paddleocrHost'),
            value: form.paddleocr_host,
            onChange: v => setForm(s => ({ ...s, paddleocr_host: v })),
            placeholder: 'https://paddleocr.aistudio-app.com',
          },
          {
            label: t('ocr.config.paddleocrModel'),
            value: form.paddleocr_model,
            onChange: v => setForm(s => ({ ...s, paddleocr_model: v })),
            placeholder: 'PaddleOCR-VL-1.6',
          },
        ]}
      />

      <BackendRow
        label={t('ocr.config.glmocr')}
        placeholder="glm-..."
        value={form.glmocr_api_key}
        onChange={v => setForm(s => ({ ...s, glmocr_api_key: v }))}
        onGetKey={() => openExternal('https://open.bigmodel.cn/usercenter/apikeys')}
        getKeyLabel={t('ocr.config.getKey')}
        onTest={() => runTest('glmocr')}
        testing={testing === 'glmocr'}
        testResult={testResults.glmocr}
      />

      {fileName && (
        <p style={{ marginTop: 16, fontSize: 11, color: 'var(--text-muted)' }}>
          {fileName}
        </p>
      )}
    </Modal>
  )
}

interface BackendRowProps {
  label: string
  placeholder: string
  value: string
  onChange: (v: string) => void
  onGetKey: () => void
  getKeyLabel: string
  onTest: () => void
  testing: boolean
  testResult: OcrTestResult | null
  extra?: Array<{
    label: string
    value: string
    onChange: (v: string) => void
    placeholder: string
  }>
}

function BackendRow({ label, placeholder, value, onChange, onGetKey, getKeyLabel, onTest, testing, testResult, extra }: BackendRowProps) {
  const { t } = useTranslation()
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 6,
      }}>
        <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
          {label}
        </label>
        <button
          type="button"
          onClick={onGetKey}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--accent)',
            fontSize: 11,
            cursor: 'pointer',
            padding: 0,
            textDecoration: 'underline',
          }}
        >
          {getKeyLabel}
        </button>
      </div>
      <ApiKeyInput value={value} onChange={onChange} placeholder={placeholder} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
        <Button variant="secondary" size="sm" onClick={onTest} loading={testing} disabled={!value.trim() || testing}>
          {t('ocr.config.test', { defaultValue: '测试' })}
        </Button>
        {testResult && (
          <span style={{
            fontSize: 11,
            color: testResult.ok ? '#16a34a' : '#dc2626',
          }}>
            {testResult.ok ? '✓ ' : '✗ '}
            {testResult.message}
          </span>
        )}
      </div>
      {extra && extra.length > 0 && (
        <div style={{ marginTop: 8, display: 'grid', gap: 6 }}>
          {extra.map(e => (
            <div key={e.label} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <label style={{ fontSize: 11, color: 'var(--text-muted)', minWidth: 80 }}>
                {e.label}
              </label>
              <input
                type="text"
                value={e.value}
                onChange={ev => e.onChange(ev.target.value)}
                placeholder={e.placeholder}
                style={{
                  flex: 1,
                  padding: '6px 8px',
                  fontSize: 12,
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  background: 'var(--bg-base)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono, monospace)',
                }}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

async function loadSaved(setForm: (s: FormState) => void) {
  try {
    const resp = await getSettings()
    if (!resp.success || !resp.settings?.ocr) return
    const o = resp.settings.ocr as unknown as Partial<FormState>
    setForm({
      mineru_api_key: o.mineru_api_key ?? '',
      uniparser_api_key: o.uniparser_api_key ?? '',
      paddleocr_api_key: o.paddleocr_api_key ?? '',
      paddleocr_host: o.paddleocr_host ?? '',
      paddleocr_model: o.paddleocr_model ?? '',
    })
  } catch {
    // ignore — empty form
  }
}