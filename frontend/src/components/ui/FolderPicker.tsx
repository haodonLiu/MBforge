import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { open } from '@tauri-apps/plugin-dialog'
import { FolderOpenIcon } from '../icons'
import Button from './Button'
import { showToast } from '../../hooks/useToast'
import { cleanWindowsPath } from '../../utils/path'


interface FolderPickerProps {
  value: string
  onChange: (path: string) => void
  placeholder?: string
  title?: string
  disabled?: boolean
}

export function FolderPicker({ 
  value, 
  onChange, 
  placeholder,
  title,
  disabled = false 
}: FolderPickerProps) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)

  const effectivePlaceholder = placeholder ?? t('folder.select')
  const effectiveTitle = title ?? t('folder.select')

  const handleSelect = async () => {
    setLoading(true)

    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title: effectiveTitle,
      })

      if (selected) {
        const raw = typeof selected === 'string' ? selected : Array.isArray(selected) ? selected[0] : ''
        if (raw) {
          onChange(cleanWindowsPath(raw))
        }
      }
    } catch (e: unknown) {
      const error = e as Error
      const msg = error?.message || String(e)
      if (msg.includes('not allowed') || msg.includes('permission')) {
        showToast(t('folder.errorPermission'), 'error')
      } else if (msg.includes('not available')) {
        showToast(t('folder.errorPlugin'), 'error')
      } else if (msg.includes('IPC')) {
        showToast(t('folder.errorIpc'), 'error')
      } else {
        showToast(t('folder.errorSelect', { msg }), 'error')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', gap: '8px' }}>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(cleanWindowsPath(e.target.value))}
        placeholder={effectivePlaceholder}
        disabled={disabled}
        style={{
          flex: 1,
          height: '40px',
          padding: '0 12px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: '8px',
          color: 'var(--text-primary)',
          fontSize: '14px',
          outline: 'none',
          boxSizing: 'border-box',
        }}
      />
      
      <Button
        variant="secondary"
        onClick={handleSelect}
        disabled={disabled || loading}
        title={t('folder.browse')}
      >
        <FolderOpenIcon size={16} />
      </Button>
    </div>
  )
}
