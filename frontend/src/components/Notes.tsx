import { useState, useMemo, useEffect, useCallback } from 'react'
import { PageContainer, PageTitle, Button, Input, EmptyState, AlertBanner } from './ui'
import { PlusIcon, SearchIcon, FlaskIcon, ClockIcon } from './icons'
import NoteEditor, { type Note } from './notes/NoteEditor'
import { showToast } from '../hooks/useToast'
import { useAppContext } from '../context/AppContext'
import { notesList, notesSave, notesDelete } from '../api/tauri/notes'
import { StaggerContainer, StaggerItem } from './animations/StaggerContainer'

function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)}天前`
  return new Date(iso).toLocaleDateString('zh-CN')
}

export default function Notes() {
  const { projectRoot } = useAppContext()
  const [notes, setNotes] = useState<Note[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)

  const loadNotes = useCallback(async () => {
    if (!projectRoot) {
      setNotes([])
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const list = await notesList(projectRoot)
      setNotes(list)
      if (list.length > 0 && !activeId) {
        setActiveId(list[0].id)
      }
    } catch (e) {
      showToast('加载笔记失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [projectRoot, activeId])

  useEffect(() => {
    loadNotes()
  }, [loadNotes])

  const activeNote = useMemo(
    () => notes.find(n => n.id === activeId) ?? null,
    [notes, activeId],
  )

  const filteredNotes = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return notes
    return notes.filter(n =>
      n.title.toLowerCase().includes(q) ||
      n.content.toLowerCase().includes(q) ||
      n.tags.some(t => t.toLowerCase().includes(q))
    )
  }, [notes, searchQuery])

  // 全部标签聚合
  const allTags = useMemo(() => {
    const set = new Set<string>()
    notes.forEach(n => n.tags.forEach(t => set.add(t)))
    return Array.from(set)
  }, [notes])

  const [activeTag, setActiveTag] = useState<string | null>(null)

  const tagFiltered = useMemo(() => {
    if (!activeTag) return filteredNotes
    return filteredNotes.filter(n => n.tags.includes(activeTag))
  }, [filteredNotes, activeTag])

  const handleCreate = async () => {
    if (!projectRoot) return
    const newNote: Note = {
      id: `note_${Date.now()}`,
      title: '新笔记',
      content: '',
      tags: [],
      links: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    try {
      const saved = await notesSave(projectRoot, newNote)
      setNotes(prev => [saved, ...prev])
      setActiveId(saved.id)
      showToast('已创建新笔记', 'success')
    } catch (e) {
      showToast('保存笔记失败', 'error')
    }
  }

  const handleUpdate = async (updated: Note) => {
    if (!projectRoot) return
    setNotes(prev => prev.map(n => n.id === updated.id ? updated : n))
    try {
      await notesSave(projectRoot, updated)
    } catch (e) {
      showToast('保存笔记失败', 'error')
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除这条笔记？此操作不可撤销。')) return
    if (!projectRoot) return
    try {
      await notesDelete(projectRoot, id)
      setNotes(prev => prev.filter(n => n.id !== id))
      if (activeId === id) {
        setActiveId(notes.find(n => n.id !== id)?.id ?? null)
      }
      showToast('笔记已删除', 'success')
    } catch (e) {
      showToast('删除笔记失败', 'error')
    }
  }

  return (
    <PageContainer>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, gap: 16, flexWrap: 'wrap' }}>
        <div>
          <PageTitle>Notes</PageTitle>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
            知识库笔记 · 共 {notes.length} 条 · 支持 Markdown 与双链
          </div>
          {loading && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              正在加载笔记...
            </div>
          )}
          {!projectRoot && (
            <div style={{ fontSize: 12, color: 'var(--warning)', marginTop: 4 }}>
              请先打开或创建一个项目
            </div>
          )}
        </div>
        <Button variant="primary" onClick={handleCreate}>
          <PlusIcon size={14} /> 新建笔记
        </Button>
      </div>

      <AlertBanner
        variant="info"
        message="使用 [[笔记名]] 创建双链，让笔记互相连接形成知识网络。支持 Markdown 语法、#标签、表格、引用块等。"
      />

      <div style={{
        display: 'grid',
        gridTemplateColumns: '320px minmax(0, 1fr)',
        gap: 16,
        marginTop: 16,
        alignItems: 'flex-start',
      }}>
        {/* 左侧：笔记列表 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* 搜索 */}
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}>
              <SearchIcon size={14} />
            </span>
            <Input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="搜索笔记内容..."
              style={{ paddingLeft: 32 }}
            />
          </div>

          {/* 标签筛选 */}
          {allTags.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              <TagPill
                label="全部"
                active={activeTag === null}
                onClick={() => setActiveTag(null)}
              />
              {allTags.map(tag => (
                <TagPill
                  key={tag}
                  label={tag}
                  active={activeTag === tag}
                  onClick={() => setActiveTag(activeTag === tag ? null : tag)}
                />
              ))}
            </div>
          )}

          {/* 笔记列表 */}
          {tagFiltered.length === 0 ? (
            <EmptyState message="没有匹配的笔记" />
          ) : (
            <StaggerContainer stagger={0.04}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {tagFiltered.map(note => (
                  <StaggerItem key={note.id}>
                    <NoteListItem
                      note={note}
                      active={activeId === note.id}
                      onClick={() => setActiveId(note.id)}
                    />
                  </StaggerItem>
                ))}
              </div>
            </StaggerContainer>
          )}
        </div>

        {/* 右侧：编辑器 */}
        <NoteEditor
          note={activeNote}
          onChange={handleUpdate}
          onDelete={handleDelete}
          wikilinkSuggestions={[]}
        />
      </div>
    </PageContainer>
  )
}

// ============================================================================
// 子组件
// ============================================================================

interface TagPillProps {
  label: string
  active: boolean
  onClick: () => void
}

function TagPill({ label, active, onClick }: TagPillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '2px 8px',
        background: active ? 'var(--accent)' : 'var(--bg-elevated)',
        color: active ? 'white' : 'var(--text-secondary)',
        border: 'none',
        borderRadius: 12,
        fontSize: 11,
        cursor: 'pointer',
        transition: 'all 0.1s',
      }}
    >
      {active ? '#' : '#'}{label}
    </button>
  )
}

interface NoteListItemProps {
  note: Note
  active: boolean
  onClick: () => void
}

function NoteListItem({ note, active, onClick }: NoteListItemProps) {
  // 提取首段纯文本作为摘要
  const excerpt = useMemo(() => {
    const text = note.content
      .replace(/^#+ .*$/gm, '')           // 标题
      .replace(/\*\*([^*]+)\*\*/g, '$1')  // bold
      .replace(/\*([^*]+)\*/g, '$1')     // italic
      .replace(/\[\[([^\]]+)\]\]/g, '$1')// wikilink
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // markdown link
      .replace(/```[\s\S]*?```/g, '')     // code blocks
      .replace(/`([^`]+)`/g, '$1')       // inline code
      .replace(/^[-*+] /gm, '')          // list markers
      .replace(/^> /gm, '')              // blockquote
      .replace(/\|/g, ' ')               // table
      .replace(/\n+/g, ' ')
      .trim()
    return text.length > 100 ? text.slice(0, 100) + '...' : text
  }, [note.content])

  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'block',
        width: '100%',
        padding: '12px 14px',
        background: active ? 'var(--accent-muted)' : 'var(--bg-surface)',
        border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
        borderRadius: 8,
        textAlign: 'left',
        cursor: 'pointer',
        transition: 'all 0.1s',
      }}
      onMouseEnter={e => {
        if (!active) e.currentTarget.style.borderColor = 'var(--accent)'
      }}
      onMouseLeave={e => {
        if (!active) e.currentTarget.style.borderColor = 'var(--border)'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{
          flex: 1,
          fontSize: 13,
          fontWeight: active ? 600 : 500,
          color: 'var(--text-primary)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {note.title || '(无标题)'}
        </span>
      </div>
      {excerpt && (
        <div style={{
          fontSize: 11,
          color: 'var(--text-muted)',
          lineHeight: 1.4,
          marginBottom: 6,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
        }}>
          {excerpt}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
          {note.tags.slice(0, 2).map(t => (
            <span key={t} style={{
              fontSize: 10,
              padding: '1px 5px',
              background: 'var(--bg-elevated)',
              borderRadius: 3,
              color: 'var(--text-muted)',
            }}>
              #{t}
            </span>
          ))}
          {note.links.length > 0 && (
            <span style={{ fontSize: 10, color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', gap: 2 }}>
              <FlaskIcon size={9} /> {note.links.length}
            </span>
          )}
        </div>
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          <ClockIcon size={9} /> {relativeTime(note.updatedAt)}
        </span>
      </div>
    </button>
  )
}
