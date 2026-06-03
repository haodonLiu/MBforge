import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence } from 'framer-motion'
import { kbSearchStream } from '../api/tauri-bridge'
import { SearchIcon, FileTextIcon } from './icons'
import { useAppContext } from '../context/AppContext'
import { tapScale } from '../hooks/useAnimations'
import PageContainer from '../components/ui/PageContainer'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
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

function mapResult(r: { text?: string; metadata?: Record<string, unknown> }, i: number): ResultItem {
  return {
    id: String(i),
    title: String(r.metadata?.doc_id || r.metadata?.title || '文档片段'),
    snippet: r.text || '',
    source: String(r.metadata?.source || r.metadata?.path || '未知来源'),
    tags: [],
    date: '',
  }
}

export default function Search() {
  const { t } = useTranslation()
  const { projectRoot } = useAppContext()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<ResultItem[]>([])
  const [hasSearched, setHasSearched] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isFocused, setIsFocused] = useState(false)
  const unlistenRef = useRef<(() => void) | null>(null)

  // 组件卸载时清理事件监听
  useEffect(() => {
    return () => { unlistenRef.current?.() }
  }, [])

  const doSearch = async (term: string) => {
    if (!projectRoot) {
      setResults([])
      setHasSearched(true)
      return
    }
    // 清理上一次搜索
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
            // 首批结果 — 立即显示
            setResults(chunk.results.map((r, i) => mapResult(r, resultIndex + i)))
            resultIndex += chunk.results.length
            setIsLoading(false)
          } else if (chunk.type === 'incremental') {
            // 增量结果 — 追加
            setResults(prev => [...prev, ...chunk.results.map((r, i) => mapResult(r, resultIndex + i))])
            resultIndex += chunk.results.length
          } else if (chunk.type === 'complete') {
            // 完成
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
      doSearch(query.trim())
    }
  }

  const quickSearch = (term: string) => {
    setQuery(term)
    doSearch(term)
  }

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
                  initial={{ opacity: 0, y: 10, transition: { delay: index * 0.05 } }}
                  animate={{ opacity: 1, y: 0, transition: { duration: 0.25, delay: index * 0.05 } }}
                  exit={{ opacity: 0 }}
                >
                  <Card hoverable>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      marginBottom: '6px',
                    }}>
                      <FileTextIcon size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                      <span style={{
                        fontSize: '12px',
                        fontWeight: 500,
                        color: 'var(--accent)',
                        opacity: 0.85,
                      }}>
                        {r.source.split(/[/\\]/).pop()}
                      </span>
                    </div>
                    <div style={{
                      fontSize: '14px',
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                      marginBottom: '6px',
                    }}>
                      {r.title}
                    </div>
                    <BodyText size="md" style={{ lineHeight: 1.65, color: 'var(--text-secondary)' }}>
                      {r.snippet}
                    </BodyText>
                    {r.tags.length > 0 && (
                      <div style={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: '6px',
                        marginTop: '10px',
                      }}>
                        {r.tags.map(tag => (
                          <Badge key={tag} variant="info">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </Card>
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


