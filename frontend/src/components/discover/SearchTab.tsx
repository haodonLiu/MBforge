import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence } from 'framer-motion'
import { kbSearchStream } from '@/api/tauri'
import { SearchIcon } from '@/components/icons'
import { useAppContext } from '@/context/AppContext'
import { tapScale } from '@/hooks/useAnimations'
import BodyText from '@/components/ui/BodyText'
import Skeleton from '@/components/ui/Skeleton'
import SearchResultItem from '@/components/search/SearchResultItem'

interface ResultItem {
  id: string
  title: string
  snippet: string
  source: string
  sourcePath: string
  page: number | null
  pageEnd: number | null
  score: number
  tags: string[]
}

type SortKey = 'relevance' | 'page'

interface SearchTabProps {
  initialQuery?: string
  onQueryChange?: (query: string) => void
}

const HINTS = ['阿司匹林', '分子对接', 'SAR分析', 'IC50']

function mapResult(
  r: { text?: string; metadata?: Record<string, unknown>; score?: number },
  i: number,
): ResultItem {
  const md = r.metadata ?? {}
  const pageStart = typeof md.page_start === 'number' ? md.page_start : null
  const pageEnd = typeof md.page_end === 'number' ? md.page_end : null
  const path = typeof md.path === 'string' ? md.path : ''
  const title = typeof md.doc_id === 'string'
    ? md.doc_id
    : typeof md.title === 'string'
      ? md.title
      : '文档片段'
  const source = typeof md.source === 'string' ? md.source : path || '未知来源'
  return {
    id: String(i),
    title,
    snippet: r.text || '',
    source,
    sourcePath: path,
    page: pageStart,
    pageEnd,
    score: typeof r.score === 'number' ? r.score : 0,
    tags: [],
  }
}

function sortResults(items: ResultItem[], key: SortKey): ResultItem[] {
  if (key === 'relevance') return items
  return [...items].sort((a, b) => {
    const ap = a.page ?? Number.MAX_SAFE_INTEGER
    const bp = b.page ?? Number.MAX_SAFE_INTEGER
    if (ap !== bp) return ap - bp
    return b.score - a.score
  })
}

export default function SearchTab({ initialQuery = '', onQueryChange }: SearchTabProps) {
  const { t } = useTranslation()
  const { projectRoot } = useAppContext()
  const [query, setQuery] = useState(initialQuery)
  const [results, setResults] = useState<ResultItem[]>([])
  const [hasSearched, setHasSearched] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isFocused, setIsFocused] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('relevance')
  const unlistenRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    return () => { unlistenRef.current?.() }
  }, [])

  useEffect(() => {
    onQueryChange?.(query)
  }, [query, onQueryChange])

  const doSearch = async (term: string) => {
    if (!projectRoot) {
      setResults([])
      setHasSearched(true)
      return
    }
    unlistenRef.current?.()
    setIsLoading(true)
    setHasSearched(true)
    setError(null)
    setResults([])

    let resultIndex = 0

    try {
      const unlisten = await kbSearchStream(
        projectRoot,
        term,
        10,
        (chunk) => {
          if (chunk.type === 'first') {
            setResults(chunk.results.map((r, i) => mapResult(r, resultIndex + i)))
            resultIndex += chunk.results.length
            setIsLoading(false)
          } else if (chunk.type === 'incremental') {
            setResults(prev => [...prev, ...chunk.results.map((r, i) => mapResult(r, resultIndex + i))])
            resultIndex += chunk.results.length
          } else {
            if (chunk.error) {
              setError(chunk.error)
            }
            setIsLoading(false)
          }
        },
      )
      unlistenRef.current = unlisten
    } catch (e) {
      setResults([])
      setError(e instanceof Error ? e.message : '搜索失败')
      setIsLoading(false)
    }
  }

  const handleSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && query.trim()) {
      void doSearch(query.trim())
    }
  }

  const quickSearch = (term: string) => {
    setQuery(term)
    void doSearch(term)
  }

  return (
    <>
      <div style={{ marginBottom: '32px' }}>
        <motion.div
          animate={{
            borderColor: isFocused ? 'var(--accent)' : 'var(--border)',
            boxShadow: isFocused ? '0 0 0 4px var(--accent-muted)' : 'none',
            scale: isFocused ? 1.01 : 1,
          }}
          transition={{ duration: 0.2 }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '16px 20px',
            background: 'var(--bg-surface)',
            border: '2px solid var(--border)',
            borderRadius: '14px',
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
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={projectRoot ? t('search.placeholder') : t('search.placeholderNoProject')}
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
        </motion.div>
        <div style={{
          display: 'flex',
          gap: '8px',
          marginTop: '12px',
        }}>
          {HINTS.map(hint => (
            <motion.button
              key={hint}
              type="button"
              onClick={() => quickSearch(hint)}
              whileTap={tapScale}
              style={{
                padding: '6px 12px',
                fontSize: '12px',
                color: 'var(--text-muted)',
                background: 'var(--bg-surface)',
                borderRadius: '6px',
                cursor: projectRoot ? 'pointer' : 'not-allowed',
                transition: 'all 0.15s',
                opacity: projectRoot ? 1 : 0.5,
                border: 'none',
                outline: 'none',
                fontFamily: 'inherit',
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
            </motion.button>
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
            gap: '12px',
            flexWrap: 'wrap',
          }}>
            <BodyText size="sm" muted>
              {isLoading ? '搜索中...' : error ? `搜索出错: ${error}` : `找到 ${results.length} 条结果`}
            </BodyText>
            <div style={{
              display: 'inline-flex',
              gap: '4px',
              padding: '2px',
              background: 'var(--bg-surface)',
              borderRadius: '8px',
              border: '1px solid var(--border)',
            }}>
              {(['relevance', 'page'] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setSortKey(k)}
                  style={{
                    padding: '4px 12px',
                    fontSize: '12px',
                    color: sortKey === k ? 'var(--accent)' : 'var(--text-muted)',
                    background: sortKey === k ? 'var(--bg-elevated)' : 'transparent',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontWeight: sortKey === k ? 600 : 400,
                    transition: 'all 0.15s',
                    fontFamily: 'inherit',
                  }}
                >
                  {k === 'relevance' ? '按相关度' : '按页码'}
                </button>
              ))}
            </div>
          </div>

          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}>
            <motion.div
              variants={{
                hidden: {},
                show: { transition: { staggerChildren: 0.05 } },
              }}
              initial="hidden"
              animate="show"
            >
              <AnimatePresence>
                {sortResults(results, sortKey).map((r) => (
                  <motion.div
                    key={r.id}
                    variants={{
                      hidden: { opacity: 0, y: 10 },
                      show: { opacity: 1, y: 0, transition: { duration: 0.25 } },
                      exit: { opacity: 0 },
                    }}
                    initial="hidden"
                    animate="show"
                    exit="exit"
                  >
                    <SearchResultItem result={r} />
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
            {isLoading && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <Skeleton variant="row" count={3} height={80} />
              </div>
            )}
          </div>
        </>
      )}
    </>
  )
}
