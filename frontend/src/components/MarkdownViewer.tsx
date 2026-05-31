import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { readFileContent } from '../api/client'
import Toolbar from './ui/Toolbar'
import IconButton from './ui/IconButton'
import Caption from './ui/Caption'
import { ArrowLeftIcon } from './icons'

interface Props {
  /** 文件绝对路径 */
  filePath: string
  /** 关闭回调 */
  onClose: () => void
}

export default function MarkdownViewer({ filePath, onClose }: Props) {
  const [content, setContent] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const filename = filePath.split(/[/\\]/).pop() || filePath

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)

    readFileContent(filePath)
      .then(resp => {
        if (cancelled) return
        if (resp.success) {
          setContent(resp.content)
        } else {
          setError(resp.error || 'Failed to load file')
        }
      })
      .catch(e => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

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
