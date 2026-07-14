import { useEffect, useState } from 'react'
import { kbListWiki, kbGetWikiSummary, kbGetWikiConcept, kbGetWikiEntity, type WikiList } from '@/api/http/kb'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Spinner from '../ui/Spinner'
import { cleanMoleculePlaceholders } from './markdownUtils'

type WikiKind = 'summary' | 'concept' | 'entity'

interface WikiDrawerProps {
  docId: string
  libraryRoot: string
  collapsed: boolean
  onToggle: () => void
}

/**
 * Right-side drawer showing the wiki summary, concepts and entities for a document.
 * Plain prose — no mermaid needed for summaries.
 */
export default function WikiDrawer({ docId, libraryRoot, collapsed, onToggle }: WikiDrawerProps) {
  const [lists, setLists] = useState<WikiList>({ summaries: [], concepts: [], entities: [] })
  const [kind, setKind] = useState<WikiKind>('summary')
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [body, setBody] = useState<string | null>(null)
  const [loadingBody, setLoadingBody] = useState(false)

  // Load the three lists once per library root
  useEffect(() => {
    let cancelled = false
    void kbListWiki(libraryRoot).then(l => {
      if (!cancelled) setLists(l)
    })
    return () => {
      cancelled = true
    }
  }, [libraryRoot])

  // Load body when kind/selection changes
  useEffect(() => {
    let cancelled = false
    setBody(null)
    if (kind === 'summary') {
      setLoadingBody(true)
      void kbGetWikiSummary(docId, libraryRoot).then(t => {
        if (cancelled) return
        setBody(t ? cleanMoleculePlaceholders(t) : null)
        setLoadingBody(false)
      })
    } else if (kind === 'concept' && selectedName) {
      setLoadingBody(true)
      void kbGetWikiConcept(selectedName, libraryRoot).then(t => {
        if (cancelled) return
        setBody(t)
        setLoadingBody(false)
      })
    } else if (kind === 'entity' && selectedName) {
      setLoadingBody(true)
      void kbGetWikiEntity(selectedName, libraryRoot).then(t => {
        if (cancelled) return
        setBody(t)
        setLoadingBody(false)
      })
    } else {
      setLoadingBody(false)
    }
    return () => {
      cancelled = true
    }
  }, [kind, selectedName, docId, libraryRoot])

  if (collapsed) {
    return (
      <div style={{
        width: 36,
        borderLeft: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        paddingTop: 12,
        gap: 8,
      }}>
        <button
          onClick={onToggle}
          title="展开 Wiki 抽屉"
          style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 18 }}
        >
          ▶
        </button>
        <div style={{ writingMode: 'vertical-rl', fontSize: 11, color: 'var(--text-muted)' }}>
          Wiki
        </div>
      </div>
    )
  }

  const items =
    kind === 'summary'
      ? lists.summaries
      : kind === 'concept'
        ? lists.concepts
        : lists.entities

  return (
    <aside
      className="wiki-drawer"
      style={{
        width: 320,
        borderLeft: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--bg-base)',
      }}
    >
      {/* Header: tabs + collapse */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        borderBottom: '1px solid var(--border)',
        padding: '6px 8px',
        gap: 4,
      }}>
        {(['summary', 'concept', 'entity'] as WikiKind[]).map(k => (
          <button
            key={k}
            onClick={() => {
              setKind(k)
              setSelectedName(null)
            }}
            style={{
              flex: 1,
              padding: '6px 4px',
              fontSize: 12,
              border: 'none',
              background: kind === k ? 'var(--bg-surface)' : 'transparent',
              color: kind === k ? 'var(--text-primary)' : 'var(--text-muted)',
              borderRadius: 4,
              cursor: 'pointer',
              fontWeight: kind === k ? 600 : 400,
            }}
          >
            {k === 'summary' ? '摘要' : k === 'concept' ? '概念' : '实体'}
          </button>
        ))}
        <button
          onClick={onToggle}
          title="收起"
          style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 14 }}
        >
          ◀
        </button>
      </div>

      {/* List of items (only for concept/entity) */}
      {kind !== 'summary' && (
        <div style={{
          flex: '0 0 auto',
          maxHeight: 160,
          overflowY: 'auto',
          borderBottom: '1px solid var(--border)',
          padding: '4px 0',
        }}>
          {items.length === 0 ? (
            <div style={{ padding: 8, color: 'var(--text-muted)', fontSize: 12 }}>
              (无)
            </div>
          ) : (
            items.map(name => (
              <button
                key={name}
                onClick={() => setSelectedName(name)}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '4px 12px',
                  fontSize: 12,
                  border: 'none',
                  background: selectedName === name ? 'var(--bg-surface)' : 'transparent',
                  color: 'var(--text-primary)',
                  cursor: 'pointer',
                }}
              >
                {name}
              </button>
            ))
          )}
        </div>
      )}

      {/* Body */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
        {loadingBody ? (
          <Spinner />
        ) : body === null ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            {kind === 'summary'
              ? '此文档尚未生成摘要'
              : '请从上方选择一个条目'}
          </div>
        ) : (
          <div className="markdown-preview" style={{ fontSize: 13 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanMoleculePlaceholders(body)}</ReactMarkdown>
          </div>
        )}
      </div>
    </aside>
  )
}
