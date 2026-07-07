import { useState, useEffect, useRef, useCallback } from 'react'
import { esmilesToMolecode } from '@/api/http/molecule'
import { Editor } from 'ketcher-react'
import { StandaloneStructServiceProvider } from 'ketcher-standalone'
import 'ketcher-react/dist/index.css'
import { XIcon } from '../icons'
import ScrollColumn from '@/components/ui/ScrollColumn'

const structServiceProvider = new StandaloneStructServiceProvider()

interface MoleculeEditorDialogProps {
  smiles: string
  name?: string
  onSave: (newSmiles: string) => void
  onClose: () => void
}

/**
 * 分子交互式编辑浮窗
 *
 * 直接使用 Ketcher 编辑器，支持：
 * - 可视化绘图编辑
 * - 导出 SMILES
 * - MoleCode 文本预览
 * - 保存覆盖原数据
 */
export default function MoleculeEditorDialog({
  smiles,
  name,
  onSave,
  onClose,
}: MoleculeEditorDialogProps) {
interface KetcherInstance {
  setMolecule: (smiles: string) => Promise<void>
  getSmiles: () => Promise<string>
}

  const ketcherRef = useRef<KetcherInstance | null>(null)
  const [saving, setSaving] = useState(false)
  const [currentSmiles, setCurrentSmiles] = useState(smiles)
  const [moleCodeText, setMoleCodeText] = useState<string | null>(null)
  const [moleCodeLoading, setMoleCodeLoading] = useState(false)

  // Ketcher 初始化后加载 SMILES
  const handleInit = useCallback((ketcher: KetcherInstance) => {
    ketcherRef.current = ketcher
    if (smiles) {
      ketcher.setMolecule(smiles).catch(() => {
        console.warn('Failed to load SMILES into Ketcher')
      })
    }
  }, [smiles])

  // 获取当前 SMILES 并更新 MoleCode
  const handleGetFromKetcher = useCallback(async () => {
    if (!ketcherRef.current) return
    try {
      const newSmiles = await ketcherRef.current.getSmiles()
      if (newSmiles) {
        setCurrentSmiles(newSmiles)
      }
    } catch (err) {
      console.error('Failed to get SMILES from Ketcher:', err)
    }
  }, [])

  // SMILES 变化时获取 MoleCode
  useEffect(() => {
    if (!currentSmiles.trim()) return
    setMoleCodeLoading(true)
    esmilesToMolecode(currentSmiles, name || 'Molecule')
      .then(setMoleCodeText)
      .catch(() => setMoleCodeText(null))
      .finally(() => setMoleCodeLoading(false))
  }, [currentSmiles, name])

  // 保存
  const handleSave = useCallback(async () => {
    if (!ketcherRef.current) return
    setSaving(true)
    try {
      const newSmiles = await ketcherRef.current.getSmiles()
      if (newSmiles) {
        onSave(newSmiles)
      }
      onClose()
    } catch (err) {
      console.error('Failed to get SMILES from Ketcher:', err)
    } finally {
      setSaving(false)
    }
  }, [onSave, onClose])

  // Escape 键关闭对话框
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        style={{
          background: 'var(--bg-surface)',
          borderRadius: 12,
          width: '90vw',
          maxWidth: 1200,
          height: '85vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
      >
        {/* 标题栏 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 16px',
            borderBottom: '1px solid var(--border)',
            background: 'var(--bg-elevated)',
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600 }}>
            分子编辑器 {name && `- ${name}`}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '6px 16px',
                background: 'var(--accent)',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 500,
                cursor: saving ? 'wait' : 'pointer',
                opacity: saving ? 0.7 : 1,
              }}
            >
              {saving ? '保存中...' : '保存'}
            </button>
            <button
              onClick={onClose}
              style={{
                padding: '6px 8px',
                background: 'var(--bg-hover)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <XIcon size={14} />
            </button>
          </div>
        </div>

        {/* 主内容区 */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* 左侧：Ketcher 编辑器 */}
          <div style={{ flex: 2, display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--border)' }}>
            <div style={{ flex: 1, minHeight: 0 }}>
              <Editor
                staticResourcesUrl="/ketcher"
                structServiceProvider={structServiceProvider}
                onInit={handleInit}
                errorHandler={(msg: string) => console.error('Ketcher:', msg)}
              />
            </div>
            {/* 从画布获取按钮 */}
            <div style={{ padding: '8px 12px', borderTop: '1px solid var(--border)' }}>
              <button
                onClick={handleGetFromKetcher}
                style={{
                  padding: '6px 12px',
                  background: 'var(--bg-elevated)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  fontSize: 12,
                  cursor: 'pointer',
                }}
              >
                ← 从画布获取 SMILES
              </button>
            </div>
          </div>

          {/* 右侧：MoleCode 文本 */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <ScrollColumn padding="12px 16px">
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--text-secondary)' }}>
                MoleCode 文本
              </div>
              <pre
                style={{
                  fontFamily: 'monospace',
                  fontSize: 11,
                  color: 'var(--text-primary)',
                  background: 'var(--bg-base)',
                  border: '1px solid var(--border)',
                  padding: '10px 12px',
                  borderRadius: 6,
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                  lineHeight: 1.5,
                  minHeight: 100,
                }}
              >
                {moleCodeLoading ? 'Loading MoleCode...' : (moleCodeText || '无法生成 MoleCode')}
              </pre>
            </ScrollColumn>
          </div>
        </div>
      </div>
    </div>
  )
}
