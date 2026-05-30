import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { kbSearch } from '../api/tauri-bridge'
import { SearchIcon, FileTextIcon, HashIcon, ClockIcon } from './icons'
import { getProjectRoot } from '../hooks/useProjectRoot'
import PageContainer from '../components/ui/PageContainer'
import HoverCard from '../components/ui/HoverCard'
import Caption from '../components/ui/Caption'
import BodyText from '../components/ui/BodyText'
import Skeleton from '../components/ui/Skeleton'

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
  const [error, setError] = useState<string | null>(null)
  const [isFocused, setIsFocused] = useState(false)

  const doSearch = async (term: string) => {
    const projectRoot = getProjectRoot()
    if (!projectRoot) {
      setResults([])
      setHasSearched(true)
      return
    }
    setIsLoading(true)
    setHasSearched(true)
    setError(null)
    try {
      const results = await kbSearch(projectRoot, term, 10)
      const mapped: ResultItem[] = results.map((r, i) => ({
        id: String(i),
        title: String(r.metadata?.doc_id || '文档片段'),
        snippet: r.text || '',
        source: String(r.metadata?.source || '未知来源'),
        tags: [],
        date: '',
      }))
      setResults(mapped)
    } catch (e) {
      setResults([])
      setError(e instanceof Error ? e.message : '搜索失败')
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
    <PageContainer>
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
              whileTap={{ scale: 0.95 }}
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
          }}>
            <BodyText size="sm" muted>
              {isLoading ? '搜索中...' : error ? `搜索出错: ${error}` : `找到 ${results.length} 条结果`}
            </BodyText>
          </div>

          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}>
            <AnimatePresence>
              {results.map((r, index) => (
                <motion.div
                  key={r.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.25, delay: index * 0.05 }}
                >
                  <HoverCard>
                    <div style={{
                      fontSize: '15px',
                      fontWeight: 600,
                      marginBottom: '8px',
                    }}>
                      {r.title}
                    </div>
                    <BodyText size="md" style={{ lineHeight: 1.6 }}>
                      {r.snippet}
                    </BodyText>
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
                  </HoverCard>
                </motion.div>
              ))}
            </AnimatePresence>
            {isLoading && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <Skeleton variant="row" count={3} height={80} />
              </div>
            )}
          </div>
        </>
      )}
    </PageContainer>
  )
}

function MetaItem({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <span style={{
      display: 'flex',
      alignItems: 'center',
      gap: '4px',
    }}>
      <span style={{ flexShrink: 0 }}>{icon}</span>
      <Caption>{text}</Caption>
    </span>
  )
}
