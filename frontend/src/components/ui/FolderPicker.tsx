import { useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { FolderOpenIcon } from '../icons'
import Button from './Button'
import { showToast } from '../../hooks/useToast'
import { isTauriAvailable } from '../../api/tauri-bridge'

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
  placeholder = '选择文件夹',
  title = '选择文件夹',
  disabled = false 
}: FolderPickerProps) {
  const [loading, setLoading] = useState(false)

  const handleSelect = async () => {
    if (!isTauriAvailable()) {
      showToast('Tauri 环境不可用，请在桌面应用中打开', 'error')
      return
    }

    setLoading(true)

    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title: title,
      })

      if (selected) {
        const raw = typeof selected === 'string' ? selected : Array.isArray(selected) ? selected[0] : ''
        if (raw) {
          const cleaned = raw.replace(/^\\\\\?\\/, '')
          onChange(cleaned)
        }
      }
    } catch (e: unknown) {
      const error = e as Error
      const msg = error?.message || String(e)
      if (msg.includes('not allowed') || msg.includes('permission')) {
        showToast('权限不足：对话框被拒绝', 'error')
      } else if (msg.includes('not available')) {
        showToast('对话框插件不可用', 'error')
      } else if (msg.includes('IPC')) {
        showToast('Tauri IPC 通信错误', 'error')
      } else {
        showToast(`选择失败: ${msg}`, 'error')
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
