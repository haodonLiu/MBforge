// 通用 API Key 输入框：带显隐切换 + 复制到剪贴板。
// 复用于 LLM / VLM / OCR / Embedding 各栏。

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import Input from '../ui/Input'
import IconButton from '../ui/IconButton'
import { EyeIcon, EyeOffIcon, CopyIcon, CheckIcon } from '../icons'

interface Props {
  value: string
  onChange: (v: string) => void
  placeholder?: string
}

export default function ApiKeyInput({ value, onChange, placeholder = 'sk-...' }: Props) {
  const { t } = useTranslation()
  const [visible, setVisible] = useState(false)
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // 忽略：剪贴板权限可能不可用
    }
  }

  return (
    <div style={{ display: 'flex', gap: '6px', alignItems: 'center', width: '100%' }}>
      <Input
        className="settings-input"
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        style={{ flex: 1, fontFamily: 'var(--font-mono, monospace)' }}
      />
      <IconButton
        size={32}
        onClick={copy}
        disabled={!value}
        title={t('common.copy')}
        aria-label={t('common.copy')}
      >
        {copied ? <CheckIcon size={16} /> : <CopyIcon size={16} />}
      </IconButton>
      <IconButton
        size={32}
        onClick={() => setVisible(v => !v)}
        title={visible ? t('settings.apiKeyHide') : t('settings.apiKeyShow')}
        aria-label={visible ? t('settings.apiKeyHide') : t('settings.apiKeyShow')}
      >
        {visible ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
      </IconButton>
    </div>
  )
}
