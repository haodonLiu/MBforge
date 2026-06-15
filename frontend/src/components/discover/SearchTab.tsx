import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence } from 'framer-motion'
import { kbSearchStream } from '@/api/tauri'
import { SearchIcon } from '@/components/icons'
import { useAppContext } from '@/context/AppContext'
import { tapScale, makeStaggerContainer, staggerItem } from '@/hooks/useAnimations'
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
  query: string
  onQueryChange: (query: string) => void
}

const stagger = makeStaggerContainer(0.05)

export default function SearchTab({ query, onQueryChange }: SearchTabProps) {
  const { t } = useTranslation()
  const { projectRoot } = useAppContext()
  const [results, setResults] = useState<ResultItem[]>([])
  const [hasSearched, setHasSearched] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isFocused, setIsFocused] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('relevance')
  const unlistenRef = useRef<(() => void) | null>(null)

  const hints = t('discover.search.hints', { returnObjects: true }) as string[]

  useEffect(() => {
    return () => { unlistenRef.current?.() }
  }, [])

  const mapResult = (
    r: { text?: string; metadata?: Record<string, unknown>; score?: number },
    i: number,
  ): ResultItem => {
    const md = r.metadata ?? {}
    const pageStart = typeof md.page_start === 'number' ? md.page_start : null
    const pageEnd = typeof md.page_end === 'number' ? md.page_end : null
    const path = typeof md.path === 'string' ? md.path : ''
    const title = typeof md.doc_id === 'string'
      ? md.doc_id
      : typeof md.title === 'string'
        ? md.title
        : t('discover.search.fallbackTitle')
    const source = typeof md.source === 'string' ? md.source : path || t('discover.search.unknownSource')
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

  const sortResults = (items: ResultItem[], key: SortKey): ResultItem[] => {
    if (key === 'relevance') return items
    return [...items].sort((a, b) => {
      const ap = a.page ?? Number.MAX_SAFE_INTEGER
      const bp = b.page ?? Number.MAX_SAFE_INTEGER
      if (ap !== bp) return ap - bp
      return b.score - a.score
    })
  }

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
      setError(e instanceof Error ? e.message : t('discover.search.searchFailed'))
      setIsLoading(false)
    }
  }

  const handleSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && query.trim()) {
      void doSearch(query.trim())
    }
  }

  const quickSearch = (term: string) => {
    onQueryChange(term)
    void doSearch(term)
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onQueryChange(e.target.value)
  }

  return (
    <>
      <div style={{ marginBottom: '32px' }}>
        <motion.div
          className="discover-search-box"
          animate={{
            borderColor: isFocused ? 'var(--accent)' : 'var(--border)',
            boxShadow: isFocused ? '0 0 0 4px var(--accent-muted)' : 'none',
            scale: isFocused ? 1.01 : 1,
          }}
          transition={{ duration: 0.2 }}
        >
          <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>
            <SearchIcon size={22} />
          </span>
          <input
            type="text"
            value={query}
            onChange={handleChange}
            onKeyDown={handleSearch}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={projectRoot ? t('discover.search.placeholder') : t('discover.search.placeholderNoProject')}
            disabled={!projectRoot}
            className="discover-search-input"
          />
        </motion.div>
        <div className="discover-search-hints">
          {hints.map(hint => (
            <motion.button
              key={hint}
              type="button"
              onClick={() => quickSearch(hint)}
              whileTap={tapScale}
              disabled={!projectRoot}
              className="discover-search-hint"
            >
              {hint}
            </motion.button>
          ))}
        </div>
      </div>

      {hasSearched && (
        <>
          <div className="discover-search-toolbar">
            <BodyText size="sm" muted>
              {isLoading
                ? t('discover.search.searching')
                : error
                  ? t('discover.search.error', { error })
                  : t('discover.search.resultsCount', { count: results.length })}
            </BodyText>
            <div className="discover-search-sort">
              {(['relevance', 'page'] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setSortKey(k)}
                  data-active={sortKey === k}
                  className="discover-search-sort-btn"
                >
                  {k === 'relevance' ? t('discover.search.sortRelevance') : t('discover.search.sortPage')}
                </button>
              ))}
            </div>
          </div>

          <div className="discover-search-results">
            <motion.div
              variants={stagger}
              initial="hidden"
              animate="show"
            >
              <AnimatePresence>
                {sortResults(results, sortKey).map((r) => (
                  <motion.div
                    key={r.id}
                    variants={staggerItem}
                    initial="hidden"
                    animate="show"
                    exit={{ opacity: 0 }}
                  >
                    <SearchResultItem result={r} />
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
            {isLoading && (
              <div className="discover-search-skeleton">
                <Skeleton variant="row" count={3} height={80} />
              </div>
            )}
          </div>
        </>
      )}
    </>
  )
}
