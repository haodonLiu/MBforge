import { useState } from 'react'
import { kbSearch } from '../api/client'
import { SearchIcon, FileTextIcon, HashIcon, ClockIcon } from './icons'
import { getProjectRoot } from '../hooks/useProjectRoot'

interface ResultItem {
  id: string
  title: string
  snippet: string
  source: string
  tags: string[]
  date: string
}

const HINTS = ['阿司匹林', '分子对接', 'SAR分析', 'IC50']

export default function Search() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<ResultItem[]>([])
  const [hasSearched, setHasSearched] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  const doSearch = async (term: string) => {
    const projectRoot = getProjectRoot()
    if (!projectRoot) {
      setResults([])
      setHasSearched(true)
      return
    }
    setIsLoading(true)
    setHasSearched(true)
    try {
      const resp = await kbSearch(projectRoot, term, 10)
      if (resp.success && resp.results) {
        const mapped: ResultItem[] = resp.results.map((r, i) => ({
          id: String(i),
          title: String(r.metadata?.doc_id || '文档片段'),
          snippet: r.text || '',
          source: String(r.metadata?.source || '未知来源'),
          tags: [],
          date: '',
        }))
        setResults(mapped)
      } else {
        setResults([])
      }
    } catch (e) {
      setResults([])
    } finally {
      setIsLoading(false)
    }
  }

  const handleSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && query.trim()) {
      doSearch(query.trim())
    }
  }

  const quickSearch = (term: string) => {
    setQuery(term)
    doSearch(term)
  }

  const projectRoot = getProjectRoot()

  return (
    <div style={{
      flex: 1,
      padding: '32px',
      overflow: 'auto',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <div style={{ marginBottom: '32px' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '16px 20px',
          background: 'var(--bg-surface)',
          border: '2px solid var(--border)',
          borderRadius: '14px',
          transition: 'all 0.2s',
        }}
        onFocus={e => {
          e.currentTarget.style.borderColor = 'var(--accent)'
          e.currentTarget.style.boxShadow = '0 0 0 4px var(--accent-muted)'
        }}
        onBlur={e => {
          e.currentTarget.style.borderColor = 'var(--border)'
          e.currentTarget.style.boxShadow = 'none'
        }}
        >
          <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>
            <SearchIcon size={22} />
          </span>
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleSearch}
            placeholder={projectRoot ? '搜索分子、文献、概念...' : '请先打开或创建一个项目'}
            disabled={!projectRoot}
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              fontSize: '16px',
              color: 'var(--text-primary)',
              fontFamily: 'inherit',
            }}
          />
        </div>
        <div style={{
          display: 'flex',
          gap: '8px',
          marginTop: '12px',
        }}>
          {HINTS.map(hint => (
            <span
              key={hint}
              onClick={() => quickSearch(hint)}
              style={{
                padding: '6px 12px',
                fontSize: '12px',
                color: 'var(--text-muted)',
                background: 'var(--bg-surface)',
                borderRadius: '6px',
                cursor: projectRoot ? 'pointer' : 'not-allowed',
                transition: 'all 0.15s',
                opacity: projectRoot ? 1 : 0.5,
              }}
              onMouseEnter={e => {
                if (!projectRoot) return
                e.currentTarget.style.background = 'var(--bg-hover)'
                e.currentTarget.style.color = 'var(--text-secondary)'
              }}
              onMouseLeave={e => {
                if (!projectRoot) return
                e.currentTarget.style.background = 'var(--bg-surface)'
                e.currentTarget.style.color = 'var(--text-muted)'
              }}
            >
              {hint}
            </span>
          ))}
        </div>
      </div>

      {hasSearched && (
        <>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '16px',
          }}>
            <span style={{
              fontSize: '13px',
              color: 'var(--text-muted)',
            }}>
              {isLoading ? '搜索中...' : `找到 ${results.length} 条结果`}
            </span>
          </div>

          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}>
            {results.map(r => (
              <div
                key={r.id}
                style={{
                  padding: '20px',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  borderRadius: '12px',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.borderColor = 'var(--accent)'
                  e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.06)'
                  e.currentTarget.style.transform = 'translateX(4px)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                  e.currentTarget.style.boxShadow = 'none'
                  e.currentTarget.style.transform = 'translateX(0)'
                }}
              >
                <div style={{
                  fontSize: '15px',
                  fontWeight: 600,
                  marginBottom: '8px',
                }}>
                  {r.title}
                </div>
                <div style={{
                  fontSize: '14px',
                  color: 'var(--text-secondary)',
                  lineHeight: 1.6,
                }}>
                  {r.snippet}
                </div>
                <div style={{
                  display: 'flex',
                  gap: '16px',
                  marginTop: '12px',
                  paddingTop: '12px',
                  borderTop: '1px solid var(--border)',
                }}>
                  <MetaItem icon={<FileTextIcon size={14} />} text={r.source} />
                  {r.tags.length > 0 && <MetaItem icon={<HashIcon size={14} />} text={r.tags.join(', ')} />}
                  {r.date && <MetaItem icon={<ClockIcon size={14} />} text={r.date} />}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function MetaItem({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <span style={{
      fontSize: '12px',
      color: 'var(--text-muted)',
      display: 'flex',
      alignItems: 'center',
      gap: '4px',
    }}>
      <span style={{ flexShrink: 0 }}>{icon}</span>
      {text}
    </span>
  )
}
