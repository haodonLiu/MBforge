import { useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'
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
  const inputRef = useRef<HTMLInputElement>(null)

  const effectivePlaceholder = placeholder ?? t('folder.select')
  const effectiveTitle = title ?? t('folder.select')

  const handleSelect = async () => {
    setLoading(true)
    try {
      inputRef.current?.click()
    } catch (e: unknown) {
      const error = e as Error
      const msg = error?.message || String(e)
      showToast(t('folder.errorSelect', { msg }), 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      const raw = files[0].webkitRelativePath || files[0].name
      if (raw) {
        onChange(cleanWindowsPath(raw))
      }
    }
  }

  return (
    <div style={{ display: 'flex', gap: '8px' }}>
      <input
        ref={inputRef}
        type="file"
        webkitdirectory=""
        onChange={handleInputChange}
        style={{ display: 'none' }}
      />
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
