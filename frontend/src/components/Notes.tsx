import { useState, useMemo, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '../i18n'
import { PageContainer, PageTitle, Button, Input, Card, Badge, EmptyState, AlertBanner } from './ui'
import { PlusIcon, SearchIcon, FlaskIcon, ClockIcon } from './icons'
import NoteEditor, { type Note } from './notes/NoteEditor'
import { showToast } from '../hooks/useToast'
import { useAppContext } from '../context/AppContext'
import { notesList, notesSave, notesDelete, notesBacklinks } from '../api/tauri/notes'
import { StaggerContainer, StaggerItem } from './animations/StaggerContainer'

function relativeTime(iso: string): string {
  const t = i18n.t.bind(i18n)
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return t('time.justNow')
  if (diff < 3600) return t('time.minutesAgo', { count: Math.floor(diff / 60) })
  if (diff < 86400) return t('time.hoursAgo', { count: Math.floor(diff / 3600) })
  if (diff < 604800) return t('time.daysAgo', { count: Math.floor(diff / 86400) })
  return new Date(iso).toLocaleDateString()
}

export default function Notes() {
  const { t } = useTranslation()
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
      showToast(t('notes.loadFailed'), 'error')
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
      title: t('notes.create'),
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
      showToast(t('notes.created'), 'success')
    } catch (e) {
      showToast(t('notes.saveFailed'), 'error')
    }
  }

  // 双链点击：按标题查找笔记并跳转
  const handleWikiLinkClick = (title: string) => {
    const target = notes.find(
      n => n.title.trim().toLowerCase() === title.trim().toLowerCase(),
    )
    if (target) {
      setActiveId(target.id)
      showToast(t('notes.jumped', { title: target.title }), 'info')
    } else {
      showToast(t('notes.notFound', { title }), 'warning')
    }
  }

  // 双链候选（自动补全）：当前所有笔记 + 占位 molecule/document 实体
  const wikilinkSuggestions = useMemo(
    () =>
      notes.map(n => ({
        id: n.id,
        title: n.title || '(无标题)',
        type: 'note' as const,
      })),
    [notes],
  )

  // 反向链接：当前活跃笔记被哪些其他笔记引用
  const [backlinks, setBacklinks] = useState<Note[]>([])
  useEffect(() => {
    if (!projectRoot || !activeId) {
      setBacklinks([])
      return
    }
    let cancelled = false
    notesBacklinks(projectRoot, activeId)
      .then(list => {
        if (!cancelled) setBacklinks(list)
      })
      .catch(() => {
        if (!cancelled) setBacklinks([])
      })
    return () => {
      cancelled = true
    }
  }, [projectRoot, activeId, notes])

  const handleUpdate = async (updated: Note) => {
    if (!projectRoot) return
    setNotes(prev => prev.map(n => n.id === updated.id ? updated : n))
    try {
      await notesSave(projectRoot, updated)
    } catch (e) {
      showToast(t('notes.saveFailed'), 'error')
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm(t('notes.confirmDelete'))) return
    if (!projectRoot) return
    try {
      await notesDelete(projectRoot, id)
      setNotes(prev => prev.filter(n => n.id !== id))
      if (activeId === id) {
        setActiveId(notes.find(n => n.id !== id)?.id ?? null)
      }
      showToast(t('notes.deleted'), 'success')
    } catch (e) {
      showToast(t('notes.deleteFailed'), 'error')
    }
  }

  return (
    <PageContainer>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, gap: 16, flexWrap: 'wrap' }}>
        <div>
          <PageTitle>{t('notes.title')}</PageTitle>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
            {t('notes.subtitle', { count: notes.length })}
          </div>
          {loading && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              {t('notes.loading')}
            </div>
          )}
          {!projectRoot && (
            <div style={{ fontSize: 12, color: 'var(--warning)', marginTop: 4 }}>
              {t('notes.noProject')}
            </div>
          )}
        </div>
        <Button variant="primary" onClick={handleCreate}>
          <PlusIcon size={14} /> {t('notes.create')}
        </Button>
      </div>

      <AlertBanner
        variant="info"
        message={t('notes.banner')}
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
              placeholder={t('notes.searchPlaceholder')}
              style={{ paddingLeft: 32 }}
            />
          </div>

          {/* 标签筛选 */}
          {allTags.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              <TagPill
                label={t('notes.allTags')}
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
            <EmptyState message={t('notes.empty')} />
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

        {/* 右侧：编辑器 + 反向链接 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <NoteEditor
            note={activeNote}
            onChange={handleUpdate}
            onDelete={handleDelete}
            wikilinkSuggestions={wikilinkSuggestions}
            onWikiLinkClick={handleWikiLinkClick}
          />
          {activeNote && <BacklinksPanel backlinks={backlinks} onJump={handleWikiLinkClick} />}
        </div>
      </div>
    </PageContainer>
  )
}

// ============================================================================
// 反向链接面板
// ============================================================================
interface BacklinksPanelProps {
  backlinks: Note[]
  onJump: (title: string) => void
}

function BacklinksPanel({ backlinks, onJump }: BacklinksPanelProps) {
  if (backlinks.length === 0) return null
  return (
    <Card padding="14px">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}
      >
        <h4 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          反向链接
        </h4>
        <Badge variant="neutral">
          {backlinks.length} 条
        </Badge>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {backlinks.map(n => (
          <button
            key={n.id}
            type="button"
            onClick={() => onJump(n.title)}
            style={{
              textAlign: 'left',
              padding: '6px 10px',
              background: 'var(--bg-base)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 12,
              color: 'var(--text-primary)',
              transition: 'all 0.1s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'var(--accent)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--border)'
            }}
          >
            <span style={{ fontWeight: 500 }}>{n.title || '(无标题)'}</span>
            <span
              style={{
                marginLeft: 8,
                fontSize: 10,
                color: 'var(--text-muted)',
              }}
            >
              {relativeTime(n.updatedAt)}
            </span>
          </button>
        ))}
      </div>
    </Card>
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

function stripMarkdown(text: string): string {
  return text
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
}

function NoteListItem({ note, active, onClick }: NoteListItemProps) {
  // 提取首段纯文本作为摘要
  const excerpt = useMemo(() => {
    const text = stripMarkdown(note.content)
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
