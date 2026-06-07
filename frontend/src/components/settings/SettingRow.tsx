// 设置行 — 字段型控件的浅包装。
// 用法：`<TextField ... />` / `<NumberField ... />` / `<SelectField ... />`
// 让每个 section 写起来像表单而不是一堆 <div> 套娃。

import type { ReactNode } from 'react'
import Input from '../ui/Input'
import { SettingItem } from '../ui/SettingSection'
import Caption from '../ui/Caption'
import ApiKeyInput from './ApiKeyInput'

// ────────── 文本字段 ──────────
export function TextField({
  label,
  description,
  value,
  onChange,
  placeholder,
  type = 'text',
  monospace,
}: {
  label: string
  description?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  type?: 'text' | 'password' | 'number'
  monospace?: boolean
}) {
  return (
    <SettingItem title={label} description={description}>
      <Input
        className="settings-input"
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          minWidth: 200,
          fontFamily: monospace ? 'var(--font-mono, monospace)' : undefined,
        }}
      />
    </SettingItem>
  )
}

// ────────── 数字字段 ──────────
export function NumberField({
  label,
  description,
  value,
  onChange,
  min,
  max,
  step = 1,
  width = 120,
  placeholder,
}: {
  label: string
  description?: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  width?: number
  placeholder?: string
}) {
  return (
    <SettingItem title={label} description={description}>
      <input
        className="settings-input"
        type="number"
        value={value || ''}
        onChange={e => {
          const raw = e.target.value
          if (raw === '') {
            onChange(0)
            return
          }
          const n = Number(raw)
          if (!Number.isFinite(n)) return
          onChange(n)
        }}
        min={min}
        max={max}
        step={step}
        placeholder={placeholder}
        style={{ width, minWidth: width, maxWidth: width, textAlign: 'right' }}
      />
    </SettingItem>
  )
}

// ────────── 下拉字段 ──────────
export function SelectField<T extends string | number>({
  label,
  description,
  value,
  onChange,
  options,
}: {
  label: string
  description?: string
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
}) {
  return (
    <SettingItem title={label} description={description}>
      <select
        className="settings-select"
        value={String(value)}
        onChange={e => {
          const v = e.target.value
          const match = options.find(o => String(o.value) === v)
          if (match) onChange(match.value)
        }}
      >
        {options.map(o => (
          <option key={String(o.value)} value={String(o.value)}>{o.label}</option>
        ))}
      </select>
    </SettingItem>
  )
}

// ────────── Toggle 开关 ──────────
export function ToggleField({
  label,
  description,
  value,
  onChange,
}: {
  label: string
  description?: string
  value: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <SettingItem title={label} description={description}>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
        className="toggle"
        style={{
          position: 'relative',
          width: 36,
          height: 20,
          borderRadius: 999,
          border: 'none',
          background: value ? 'var(--accent)' : 'var(--bg-hover)',
          cursor: 'pointer',
          transition: 'background 0.15s',
          padding: 0,
        }}
      >
        <span
          style={{
            position: 'absolute',
            top: 2,
            left: value ? 18 : 2,
            width: 16,
            height: 16,
            borderRadius: '50%',
            background: '#fff',
            transition: 'left 0.15s',
            boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
          }}
        />
      </button>
    </SettingItem>
  )
}

// ────────── 自定义内容（用于嵌套子布局）──────────
export function CustomField({
  label,
  description,
  children,
}: {
  label: string
  description?: string
  children: ReactNode
}) {
  return (
    <SettingItem title={label} description={description} layout="stacked">
      <div style={{ width: '100%' }}>{children}</div>
    </SettingItem>
  )
}

// ────────── Provider + 联动 Base URL + 可选 API Key ──────────
// 统一处理 "Provider 切换 → baseUrl 联动"。当 baseUrl 仍为默认值时，
// 切换 provider 自动填入新默认；用户自定义的值不会被覆盖。
export function ProviderField({
  label,
  description,
  provider,
  onProviderChange,
  baseUrl,
  onBaseUrlChange,
  apiKey,
  onApiKeyChange,
  providerOptions,
  needsKey,
  baseUrlPlaceholder,
  showBaseUrl = true,
}: {
  label: string
  description?: string
  provider: string
  onProviderChange: (p: string) => void
  baseUrl: string
  onBaseUrlChange: (u: string) => void
  apiKey: string
  onApiKeyChange: (k: string) => void
  providerOptions: { value: string; label: string }[]
  needsKey: boolean
  baseUrlPlaceholder?: string
  showBaseUrl?: boolean
}) {
  return (
    <>
      <SettingItem title={label} description={description}>
        <select
          className="settings-select"
          value={provider}
          onChange={e => onProviderChange(e.target.value)}
        >
          {providerOptions.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </SettingItem>
      {showBaseUrl && (
        <TextField
          label="Base URL"
          value={baseUrl}
          onChange={onBaseUrlChange}
          placeholder={baseUrlPlaceholder}
          monospace
        />
      )}
      {needsKey && (
        <SettingItem title="API Key">
          <ApiKeyInput value={apiKey} onChange={onApiKeyChange} />
        </SettingItem>
      )}
    </>
  )
}

export { ApiKeyInput, Caption }
