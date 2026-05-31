import { useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { FolderOpenIcon } from '../icons'
import Button from './Button'
import { showToast } from '../../hooks/useToast'

interface FolderPickerProps {
  value: string
  onChange: (path: string) => void
  placeholder?: string
  title?: string
  disabled?: boolean
}

/**
 * Folder picker using native Tauri dialog.
 * Requires Tauri runtime - no browser fallback.
 */
export function FolderPicker({ 
  value, 
  onChange, 
  placeholder = '选择文件夹',
  title = '选择文件夹',
  disabled = false 
}: FolderPickerProps) {
  const [loading, setLoading] = useState(false)

  const handleSelect = async () => {
    setLoading(true)
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title,
      })
      if (selected && typeof selected === 'string') {
        onChange(selected)
      }
    } catch (e) {
      showToast(`选择失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', gap: '8px' }}>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
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
        title="浏览文件夹"
      >
        <FolderOpenIcon size={16} />
      </Button>
    </div>
  )
}
