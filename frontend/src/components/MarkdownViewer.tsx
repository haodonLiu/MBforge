import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { readTextFile } from '../api/tauri-bridge'
import Toolbar from './ui/Toolbar'
import IconButton from './ui/IconButton'
import Caption from './ui/Caption'
import { ArrowLeftIcon } from './icons'

interface Props {
  /** 项目根目录绝对路径 */
  projectRoot: string
  /** 文件绝对路径 */
  filePath: string
  /** 关闭回调 */
  onClose: () => void
}

export default function MarkdownViewer({ projectRoot, filePath, onClose }: Props) {
  const [content, setContent] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const filename = filePath.split(/[/\\]/).pop() || filePath

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)

    const load = async () => {
      try {
        const text = await readTextFile(projectRoot, filePath)
        if (!cancelled) setContent(text)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    load()

    return () => { cancelled = true }
  }, [filePath])

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* 工具栏 */}
      <Toolbar style={{ justifyContent: 'flex-start', gap: '12px', height: '48px', padding: '0 16px' }}>
        <IconButton size={32} onClick={onClose}>
          <ArrowLeftIcon size={18} />
        </IconButton>
        <Caption truncate style={{ fontSize: '13px', fontWeight: 500 }}>
          {filename}
        </Caption>
      </Toolbar>

      {/* Markdown 内容 */}
      <div style={{
        flex: 1,
        overflow: 'auto',
        padding: '24px 32px',
        maxWidth: '900px',
        margin: '0 auto',
        width: '100%',
      }}>
        {isLoading ? (
          <div style={{
            textAlign: 'center', padding: '40px',
            color: 'var(--text-muted)', fontSize: '13px',
          }}>
            加载中...
          </div>
        ) : error ? (
          <div style={{
            textAlign: 'center', padding: '40px',
            color: 'var(--danger)', fontSize: '13px',
          }}>
            {error}
          </div>
        ) : (
          <div className="markdown-preview">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
