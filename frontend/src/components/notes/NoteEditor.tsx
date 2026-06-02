import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Button from '../ui/Button'
import { ExternalLinkIcon } from '../icons'

// ============================================================================
// 简易富文本工具栏按钮
// ============================================================================

interface ToolbarButtonProps {
  onClick: () => void
  active?: boolean
  title: string
  children: React.ReactNode
}

function ToolbarButton({ onClick, active, title, children }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 28,
        height: 28,
        borderRadius: 4,
        border: 'none',
        background: active ? 'var(--accent-muted)' : 'transparent',
        color: active ? 'var(--accent)' : 'var(--text-secondary)',
        cursor: 'pointer',
        transition: 'all 0.1s',
      }}
      onMouseEnter={e => {
        if (!active) e.currentTarget.style.background = 'var(--bg-hover)'
      }}
      onMouseLeave={e => {
        if (!active) e.currentTarget.style.background = 'transparent'
      }}
    >
      {children}
    </button>
  )
}

// ============================================================================
// BoldIcon / ItalicIcon / etc. — 简易内联 SVG
// ============================================================================

const BoldIcon = () => (
  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 4h8a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z" />
    <path d="M6 12h9a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z" />
  </svg>
)
const ItalicIcon = () => (
  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <line x1="19" y1="4" x2="10" y2="4" />
    <line x1="14" y1="20" x2="5" y2="20" />
    <line x1="15" y1="4" x2="9" y2="20" />
  </svg>
)
const ListIcon = () => (
  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <line x1="8" y1="6" x2="21" y2="6" />
    <line x1="8" y1="12" x2="21" y2="12" />
    <line x1="8" y1="18" x2="21" y2="18" />
    <line x1="3" y1="6" x2="3.01" y2="6" />
    <line x1="3" y1="12" x2="3.01" y2="12" />
    <line x1="3" y1="18" x2="3.01" y2="18" />
  </svg>
)
const HashIcon = () => (
  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <line x1="4" y1="9" x2="20" y2="9" />
    <line x1="4" y1="15" x2="20" y2="15" />
    <line x1="10" y1="3" x2="8" y2="21" />
    <line x1="16" y1="3" x2="14" y2="21" />
  </svg>
)
const SaveIcon = () => (
  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
    <polyline points="17 21 17 13 7 13 7 21" />
    <polyline points="7 3 7 8 15 8" />
  </svg>
)
const EditIcon = () => (
  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
  </svg>
)
const LinkIcon = () => (
  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
  </svg>
)

// ============================================================================
// 类型
// ============================================================================

export interface Note {
  id: string
  title: string
  content: string
  tags: string[]
  /** 关联的实体 */
  links: NoteLink[]
  createdAt: string
  updatedAt: string
}

export interface NoteLink {
  type: 'molecule' | 'document' | 'session' | 'note'
  refId: string
  refTitle: string
}

// ============================================================================
// 主组件
// ============================================================================

export interface NoteEditorProps {
  note: Note | null
  onChange: (note: Note) => void
  onDelete?: (id: string) => void
  /** 双链候选（点击 [[ 可触发） */
  wikilinkSuggestions?: Array<{ id: string; title: string; type: NoteLink['type'] }>
  /** 点击 [[Title]] wikilink 时触发（由父组件实现跳转逻辑） */
  onWikiLinkClick?: (title: string) => void
  className?: string
  style?: React.CSSProperties
}
export default function NoteEditor({
  note,
  onChange,
  onDelete,
  wikilinkSuggestions = [],
  onWikiLinkClick,
  className,
  style,
}: NoteEditorProps) {
  const { t } = useTranslation()
  const [isEditing, setIsEditing] = useState(false)
  const [draft, setDraft] = useState(note)
  const [showWikilinkMenu, setShowWikilinkMenu] = useState(false)
  const [wikilinkFilter, setWikilinkFilter] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    setDraft(note)
    if (!note) setIsEditing(false)
  }, [note])

  if (!note) {
    return (
      <div
        className={className}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
          fontSize: 14,
          background: 'var(--bg-surface)',
          border: '1px dashed var(--border)',
          borderRadius: 12,
          padding: 40,
          ...style,
        }}
      >
        {t('notes.noSelection')}
      </div>
    )
  }

  const handleSave = () => {
    onChange({ ...draft!, updatedAt: new Date().toISOString() })
    setIsEditing(false)
  }

  const handleCancel = () => {
    setDraft(note)
    setIsEditing(false)
  }

  // 工具栏操作
  const wrapSelection = (before: string, after = before) => {
    if (!textareaRef.current) return
    const ta = textareaRef.current
    const start = ta.selectionStart
    const end = ta.selectionEnd
    const text = draft!.content
    const selected = text.slice(start, end)
    const newText = text.slice(0, start) + before + selected + after + text.slice(end)
    setDraft({ ...draft!, content: newText })
    setTimeout(() => {
      ta.focus()
      ta.setSelectionRange(start + before.length, end + before.length)
    }, 0)
  }

  const insertLinePrefix = (prefix: string) => {
    if (!textareaRef.current) return
    const ta = textareaRef.current
    const start = ta.selectionStart
    const text = draft!.content
    const lineStart = text.lastIndexOf('\n', start - 1) + 1
    const newText = text.slice(0, lineStart) + prefix + text.slice(lineStart)
    setDraft({ ...draft!, content: newText })
    setTimeout(() => {
      ta.focus()
      ta.setSelectionRange(start + prefix.length, start + prefix.length)
    }, 0)
  }

  // 当输入 [[ 时显示候选
  const handleTextChange = (value: string) => {
    setDraft({ ...draft!, content: value })
    const cursor = textareaRef.current?.selectionStart ?? 0
    const before = value.slice(0, cursor)
    const lastOpen = before.lastIndexOf('[[')
    const lastClose = before.lastIndexOf(']]')
    if (lastOpen > lastClose && lastOpen >= cursor - 30) {
      setShowWikilinkMenu(true)
      setWikilinkFilter(before.slice(lastOpen + 2))
    } else {
      setShowWikilinkMenu(false)
    }
  }

  const insertWikilink = (title: string) => {
    if (!textareaRef.current) return
    const ta = textareaRef.current
    const cursor = ta.selectionStart
    const text = draft!.content
    const before = text.slice(0, cursor)
    const lastOpen = before.lastIndexOf('[[')
    const newText = text.slice(0, lastOpen) + `[[${title}]]` + text.slice(cursor)
    setDraft({ ...draft!, content: newText })
    setShowWikilinkMenu(false)
    setTimeout(() => {
      ta.focus()
      const newCursor = lastOpen + title.length + 4
      ta.setSelectionRange(newCursor, newCursor)
    }, 0)
  }

  const filteredSuggestions = wikilinkSuggestions.filter(s =>
    s.title.toLowerCase().includes(wikilinkFilter.toLowerCase())
  ).slice(0, 5)

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        overflow: 'hidden',
        ...style,
      }}
    >
      {/* Header */}
      <div style={{
        padding: '14px 16px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
      }}>
        {isEditing ? (
          <input
            type="text"
            value={draft!.title}
            onChange={e => setDraft({ ...draft!, title: e.target.value })}
            placeholder={t('notes.titlePlaceholder')}
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              fontSize: 16,
              fontWeight: 600,
              color: 'var(--text-primary)',
            }}
          />
        ) : (
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
              {note.title || t('notes.untitled')}
            </h2>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
              最后更新：{new Date(note.updatedAt).toLocaleString('zh-CN')}
            </div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 6 }}>
          {isEditing ? (
            <>
              <Button size="sm" variant="secondary" onClick={handleCancel}>取消</Button>
              <Button size="sm" variant="primary" onClick={handleSave}><SaveIcon /> 保存</Button>
            </>
          ) : (
            <>
              {onDelete && (
                <Button size="sm" variant="ghost" onClick={() => onDelete(note.id)} title="删除">
                  <TrashIconSvg />
                </Button>
              )}
              <Button size="sm" variant="primary" onClick={() => setIsEditing(true)}>
                <EditIcon /> 编辑
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Toolbar (only when editing) */}
      {isEditing && (
        <div style={{
          padding: '6px 12px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          background: 'var(--bg-base)',
          position: 'relative',
        }}>
          <ToolbarButton title="加粗" onClick={() => wrapSelection('**')}><BoldIcon /></ToolbarButton>
          <ToolbarButton title="斜体" onClick={() => wrapSelection('*')}><ItalicIcon /></ToolbarButton>
          <ToolbarButton title="列表" onClick={() => insertLinePrefix('- ')}><ListIcon /></ToolbarButton>
          <ToolbarButton title="标题" onClick={() => insertLinePrefix('# ')}><HashIcon /></ToolbarButton>
          <ToolbarButton title="双链" onClick={() => wrapSelection('[[', ']]')}><LinkIcon /></ToolbarButton>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            支持 Markdown · 输入 [[ 插入双链
          </span>

          {/* Wikilink Menu */}
          {showWikilinkMenu && filteredSuggestions.length > 0 && (
            <div style={{
              position: 'absolute',
              top: '100%',
              left: 12,
              marginTop: 4,
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              zIndex: 10,
              minWidth: 200,
              maxHeight: 240,
              overflowY: 'auto',
            }}>
              {filteredSuggestions.map(s => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => insertWikilink(s.title)}
                  style={{
                    display: 'block',
                    width: '100%',
                    padding: '8px 12px',
                    background: 'transparent',
                    border: 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    color: 'var(--text-primary)',
                    fontSize: 13,
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <div style={{ fontWeight: 500 }}>{s.title}</div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>{s.type}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '20px 24px' }}>
        {isEditing ? (
          <textarea
            ref={textareaRef}
            value={draft!.content}
            onChange={e => handleTextChange(e.target.value)}
            placeholder={t('notes.placeholder')}
            style={{
              width: '100%',
              minHeight: 400,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              fontSize: 14,
              lineHeight: 1.7,
              color: 'var(--text-primary)',
              fontFamily: 'inherit',
              resize: 'vertical',
              boxSizing: 'border-box',
            }}
          />
        ) : (
          <div className="note-content" style={{
            fontSize: 14,
            lineHeight: 1.7,
            color: 'var(--text-primary)',
          }}>
            {note.content.trim() ? (
              <MarkdownWithWikiLinks
                content={note.content}
                onWikiLinkClick={onWikiLinkClick}
                t={t}
              />
            ) : (
              <p style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                {t('notes.emptyNote')}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Footer: 标签 + 链接 */}
      {note.tags.length > 0 || note.links.length > 0 ? (
        <div style={{
          padding: '10px 16px',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
          fontSize: 12,
          color: 'var(--text-muted)',
        }}>
          {note.tags.length > 0 && (
            <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
              <span>标签：</span>
              {note.tags.map(tag => (
                <span key={tag} style={{
                  padding: '2px 8px',
                  background: 'var(--bg-elevated)',
                  borderRadius: 4,
                  color: 'var(--text-secondary)',
                  fontSize: 11,
                }}>
                  #{tag}
                </span>
              ))}
            </div>
          )}
          {note.links.length > 0 && (
            <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
              <span>引用：</span>
              {note.links.map((l, i) => (
                <a key={i} href="#" onClick={e => e.preventDefault()} style={{
                  color: 'var(--accent)',
                  textDecoration: 'none',
                }} title={`${l.type}: ${l.refTitle}`}>
                  <ExternalLinkIcon size={10} /> {l.refTitle}
                </a>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}

// ============================================================================
// 渲染 Markdown + WikiLinks
// ============================================================================

interface MarkdownWithWikiLinksProps {
  content: string
  onWikiLinkClick?: (title: string) => void
  t: (key: string, options?: Record<string, unknown>) => string
}

function MarkdownWithWikiLinks({ content, onWikiLinkClick, t }: MarkdownWithWikiLinksProps) {
  // 先把 [[X]] 转成自定义语法，markdown 不支持
  const preprocessed = content.replace(/\[\[([^\]]+)\]\]/g, (_match, title) => {
    return `[${title}](#wiki/${encodeURIComponent(title)})`
  })

  return (
    <div>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // 自定义链接：检测 wiki 链接
          a: ({ node, ...props }) => {
            const href = props.href ?? ''
            if (href.startsWith('#wiki/')) {
              const title = decodeURIComponent(href.slice(6))
              return (
                <a
                  href={href}
                  onClick={e => {
                    e.preventDefault()
                    if (onWikiLinkClick) {
                      onWikiLinkClick(title)
                    }
                  }}
                  style={{
                    color: 'var(--accent)',
                    background: 'var(--accent-muted)',
                    padding: '1px 4px',
                    borderRadius: 3,
                    textDecoration: 'none',
                    fontSize: '0.9em',
                    cursor: onWikiLinkClick ? 'pointer' : 'help',
                  }}
                  title={onWikiLinkClick ? t('notes.jumpTo', { title }) : t('notes.unlinked', { title })}
                >
                  {props.children}
                </a>
              )
            }
            return <a {...props} style={{ color: 'var(--accent)' }} target="_blank" rel="noopener noreferrer" />
          },
          h1: ({ children }) => <h1 style={{ fontSize: 22, fontWeight: 600, margin: '20px 0 10px' }}>{children}</h1>,
          h2: ({ children }) => <h2 style={{ fontSize: 18, fontWeight: 600, margin: '18px 0 8px' }}>{children}</h2>,
          h3: ({ children }) => <h3 style={{ fontSize: 15, fontWeight: 600, margin: '14px 0 6px' }}>{children}</h3>,
          p: ({ children }) => <p style={{ margin: '8px 0' }}>{children}</p>,
          code: ({ className, children, ...props }) => {
            const isBlock = className?.startsWith('language-')
            if (isBlock) {
              return (
                <pre style={{
                  background: 'var(--bg-base)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  padding: '10px 12px',
                  overflowX: 'auto',
                  fontSize: 12,
                  fontFamily: 'monospace',
                }}>
                  <code className={className} {...props}>{children}</code>
                </pre>
              )
            }
            return <code style={{ background: 'var(--bg-elevated)', padding: '1px 4px', borderRadius: 3, fontFamily: 'monospace', fontSize: '0.9em' }}>{children}</code>
          },
          ul: ({ children }) => <ul style={{ paddingLeft: 20, margin: '8px 0' }}>{children}</ul>,
          ol: ({ children }) => <ol style={{ paddingLeft: 20, margin: '8px 0' }}>{children}</ol>,
          blockquote: ({ children }) => (
            <blockquote style={{
              margin: '8px 0',
              padding: '6px 12px',
              borderLeft: '3px solid var(--accent)',
              background: 'var(--bg-base)',
              color: 'var(--text-secondary)',
            }}>{children}</blockquote>
          ),
        }}
      >
        {preprocessed}
      </ReactMarkdown>
    </div>
  )
}

// 简易删除图标（内联）
const TrashIconSvg = () => (
  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6" />
  </svg>
)
