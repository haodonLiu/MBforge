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
    console.log('[FolderPicker] === handleSelect START ===')
    console.log('[FolderPicker] Title:', title)
    console.log('[FolderPicker] Tauri available:', isTauriAvailable())
    console.log('[FolderPicker] Current value:', value)
    
    if (!isTauriAvailable()) {
      console.error('[FolderPicker] Tauri is NOT available!')
      showToast('Tauri 环境不可用，请在桌面应用中打开', 'error')
      return
    }
    
    setLoading(true)
    
    try {
      console.log('[FolderPicker] Calling dialog open...')
      const startTime = Date.now()
      
      const selected = await open({
        directory: true,
        multiple: false,
        title: title,
      })
      
      const elapsed = Date.now() - startTime
      console.log('[FolderPicker] Dialog returned after', elapsed, 'ms')
      console.log('[FolderPicker] Selected value:', JSON.stringify(selected))
      console.log('[FolderPicker] Selected type:', typeof selected)
      
      if (selected) {
        const raw = typeof selected === 'string' ? selected : Array.isArray(selected) ? selected[0] : ''
        if (raw) {
          const cleaned = raw.replace(/^\\\\\?\\/, '')
          console.log('[FolderPicker] Path selected:', raw, '→ cleaned:', cleaned)
          onChange(cleaned)
        }
      } else {
        console.log('[FolderPicker] Dialog was cancelled (null/undefined)')
      }
    } catch (e: unknown) {
      const error = e as Error
      console.error('[FolderPicker] === ERROR ===')
      console.error('[FolderPicker] Error name:', error?.name)
      console.error('[FolderPicker] Error message:', error?.message)
      console.error('[FolderPicker] Error stack:', error?.stack)
      console.error('[FolderPicker] Full error:', error)
      
      // Try to extract more details
      if (typeof e === 'object') {
        console.error('[FolderPicker] Error details:', JSON.stringify(e, null, 2))
      }
      
      // Check for common error patterns
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
      console.log('[FolderPicker] === handleSelect END ===')
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
