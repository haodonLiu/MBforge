import { useState, useEffect, useCallback, type ChangeEvent, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from '../ui'
import EditorToolbar from './editor/EditorToolbar'
import EditView from './editor/EditView'
import MarkdownWithWikiLinks from './editor/MarkdownWithWikiLinks'
import type { Note, NoteLink } from './editor/types'

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
  const [draftTitle, setDraftTitle] = useState('')
  const [draftContent, setDraftContent] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [linkStartPos, setLinkStartPos] = useState(0)

  useEffect(() => {
    if (note) {
      setDraftTitle(note.title)
      setDraftContent(note.content)
    }
  }, [note?.id])

  // ---------- 插入辅助 ----------

  const insertAround = useCallback(
    (before: string, after: string, defaultText: string) => {
      const ta = document.getElementById(
        'note-content-textarea',
      ) as HTMLTextAreaElement | null
      if (!ta) return
      const start = ta.selectionStart
      const end = ta.selectionEnd
      const selected = draftContent.slice(start, end) || defaultText
      const newContent =
        draftContent.slice(0, start) + before + selected + after + draftContent.slice(end)
      setDraftContent(newContent)
      setTimeout(() => {
        ta.focus()
        const cursorPos = start + before.length + selected.length
        ta.setSelectionRange(cursorPos, cursorPos)
      }, 0)
    },
    [draftContent],
  )

  const insertAtCursor = useCallback(
    (text: string) => {
      const ta = document.getElementById(
        'note-content-textarea',
      ) as HTMLTextAreaElement | null
      if (!ta) return
      const start = ta.selectionStart
      const newContent = draftContent.slice(0, start) + text + draftContent.slice(start)
      setDraftContent(newContent)
      setTimeout(() => {
        ta.focus()
        const cursorPos = start + text.length
        ta.setSelectionRange(cursorPos, cursorPos)
      }, 0)
    },
    [draftContent],
  )

  // ---------- 事件处理 ----------

  const handleContentChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      const value = e.target.value
      setDraftContent(value)
      // 检测 [[ 输入 → 触发建议列表
      const cursorPos = e.target.selectionStart
      const before = value.slice(0, cursorPos)
      const match = before.match(/\[\[([^\]]*)$/)
      if (match) {
        setLinkStartPos(cursorPos - match[1].length - 2)
        setShowSuggestions(true)
      } else {
        setShowSuggestions(false)
      }
    },
    [],
  )

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        handleSave()
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [draftTitle, draftContent, note],
  )

  const insertWikilink = useCallback(
    (title: string) => {
      const before = draftContent.slice(0, linkStartPos)
      const after = draftContent.slice(linkStartPos)
      // 替换 [[...]] 为 [[title]]
      const newContent = before + `[[${title}]]` + after.slice(after.indexOf(']]') + 2)
      setDraftContent(newContent)
      setShowSuggestions(false)
    },
    [draftContent, linkStartPos],
  )

  const handleSave = useCallback(() => {
    if (!note) return
    onChange({
      ...note,
      title: draftTitle,
      content: draftContent,
      updatedAt: new Date().toISOString(),
    })
    setIsEditing(false)
  }, [note, onChange, draftTitle, draftContent])

  // 自动保存：内容变化后 1.5 秒自动保存（防抖）
  useEffect(() => {
    if (!note || !isEditing) return
    // 跳过初始加载
    if (draftContent === note.content && draftTitle === note.title) return

    const timer = setTimeout(() => {
      onChange({
        ...note,
        title: draftTitle,
        content: draftContent,
        updatedAt: new Date().toISOString(),
      })
    }, 1500)

    return () => clearTimeout(timer)
  }, [note, draftContent, draftTitle, isEditing, onChange])

  const handleDelete = useCallback(() => {
    if (!note || !onDelete) return
    if (confirm(t('notes.confirmDelete'))) onDelete(note.id)
  }, [note, onDelete, t])

  // ---------- 渲染 ----------

  if (!note) {
    return (
      <div
        className={className}
        style={{
          padding: 40,
          textAlign: 'center',
          color: 'var(--text-muted)',
          ...style,
        }}
      >
        {t('notes.noNoteSelected')}
      </div>
    )
  }

  return (
    <Card className={className} style={style} padding={0}>
      <EditorToolbar
        isEditing={isEditing}
        onBold={() => insertAround('**', '**', 'bold')}
        onItalic={() => insertAround('*', '*', 'italic')}
        onList={() => insertAtCursor('\n- ')}
        onHeading={() => insertAtCursor('\n# ')}
        onExternalLink={() => insertAround('[', '](url)', 'link')}
        onSave={handleSave}
        onEdit={() => setIsEditing(true)}
        onDelete={onDelete ? handleDelete : undefined}
      />

      {isEditing ? (
        <input
          id="note-title-input"
          type="text"
          value={draftTitle}
          onChange={e => setDraftTitle(e.target.value)}
          placeholder={t('notes.titlePlaceholder')}
          style={{
            width: '100%',
            padding: '12px 16px',
            fontSize: 18,
            fontWeight: 600,
            background: 'transparent',
            border: 'none',
            borderBottom: '1px solid var(--border)',
            color: 'var(--text-primary)',
            outline: 'none',
          }}
        />
      ) : (
        <div
          style={{
            padding: '12px 16px',
            fontSize: 18,
            fontWeight: 600,
            color: 'var(--text-primary)',
            borderBottom: '1px solid var(--border)',
          }}
        >
          {note.title || t('notes.untitled')}
        </div>
      )}

      {isEditing ? (
        <EditView
          draftContent={draftContent}
          onContentChange={handleContentChange}
          onKeyDown={handleKeyDown}
          showSuggestions={showSuggestions}
          wikilinkSuggestions={wikilinkSuggestions}
          onSelectSuggestion={insertWikilink}
        />
      ) : (
        <div className="note-content" style={{ padding: '14px 16px' }}>
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
    </Card>
  )
}

// 重导出类型供父组件 (Notes.tsx) 使用
export type { Note, NoteLink } from './editor/types'
