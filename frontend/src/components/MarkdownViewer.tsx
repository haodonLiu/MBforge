import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { readTextFile } from '../api/http'
import Toolbar from './ui/Toolbar'
import IconButton from './ui/IconButton'
import Caption from './ui/Caption'
import { ArrowLeftIcon, HashIcon, NoteIcon } from './icons'

interface Props {
  /** 项目根目录绝对路径 */
  libraryRoot: string
  /** 文件绝对路径 */
  filePath: string
  /** 关闭回调 */
  onClose: () => void
}

export default function MarkdownViewer({ libraryRoot, filePath, onClose }: Props) {
  const { t } = useTranslation()
  const [content, setContent] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'rendered' | 'source'>('rendered')

  const filename = filePath.split(/[/\\]/).pop() || filePath

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)

    const load = async () => {
      try {
        const text = await readTextFile(libraryRoot, filePath)
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
        <Caption truncate style={{ fontSize: '13px', fontWeight: 500, flex: 1 }}>
          {filename}
        </Caption>

        {/* 渲染 / 源码 切换 */}
        <div style={{
          display: 'flex',
          gap: '2px',
          background: 'var(--bg-base)',
          borderRadius: '6px',
          padding: '2px',
        }}>
          <button
            onClick={() => setViewMode('rendered')}
            style={{
              padding: '4px 10px',
              fontSize: '11px',
              borderRadius: '4px',
              border: 'none',
              background: viewMode === 'rendered' ? 'var(--bg-surface)' : 'transparent',
              color: viewMode === 'rendered' ? 'var(--text-primary)' : 'var(--text-muted)',
              cursor: 'pointer',
              fontWeight: viewMode === 'rendered' ? 600 : 400,
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
            title={t('md.preview')}
          >
            <NoteIcon size={11} /> {t('md.preview')}
          </button>
          <button
            onClick={() => setViewMode('source')}
            style={{
              padding: '4px 10px',
              fontSize: '11px',
              borderRadius: '4px',
              border: 'none',
              background: viewMode === 'source' ? 'var(--bg-surface)' : 'transparent',
              color: viewMode === 'source' ? 'var(--text-primary)' : 'var(--text-muted)',
              cursor: 'pointer',
              fontWeight: viewMode === 'source' ? 600 : 400,
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
            title={t('md.source')}
          >
            <HashIcon size={11} /> {t('md.source')}
          </button>
        </div>
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
            {t('common.loading')}
          </div>
        ) : error ? (
          <div style={{
            textAlign: 'center', padding: '40px',
            color: 'var(--danger)', fontSize: '13px',
          }}>
            {error}
          </div>
        ) : viewMode === 'rendered' ? (
          <div className="markdown-preview">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
              {content}
            </ReactMarkdown>
          </div>
        ) : (
          <pre style={{
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            fontSize: '12px',
            lineHeight: 1.6,
            color: 'var(--text-secondary)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}>
            {content}
          </pre>
        )}
      </div>
    </div>
  )
}
