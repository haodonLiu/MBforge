import { useTranslation } from 'react-i18next'
import { FileTextIcon } from '../icons'
import Card from '../ui/Card'
import BodyText from '../ui/BodyText'
import Badge from '../ui/Badge'
import { showToast } from '../../hooks/useToast'

export interface SearchResultItemData {
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

export interface SearchResultItemProps {
  result: SearchResultItemData
}

type ScoreBand = 'high' | 'mid' | 'low'

function scoreBand(score: number): ScoreBand {
  if (score >= 0.7) return 'high'
  if (score >= 0.4) return 'mid'
  return 'low'
}

const BAND_VARIANT: Record<ScoreBand, 'success' | 'warning' | 'neutral'> = {
  high: 'success',
  mid: 'warning',
  low: 'neutral',
}

const BAND_LABEL: Record<ScoreBand, string> = {
  high: 'search.highlyRelevant',
  mid: 'search.relevant',
  low: 'search.reference',
}

function pageLabel(page: number | null, pageEnd: number | null, t: (key: string, opts?: Record<string, unknown>) => string): string | null {
  if (page == null) return null
  if (pageEnd != null && pageEnd !== page) return t('search.pageRange', { start: page, end: pageEnd })
  return t('search.singlePage', { page })
}

/**
 * 搜索结果单项组件。
 */
export default function SearchResultItem({ result }: SearchResultItemProps) {
  const { t } = useTranslation()
  const band = scoreBand(result.score)
  const variant = BAND_VARIANT[band]
  const scoreLabel = `${(result.score * 100).toFixed(0)}%`
  const pageText = pageLabel(result.page, result.pageEnd, t)

  // Source click currently shows a "coming soon" toast. The full
  // openDocument(docId, page) integration is tracked at TODO/INDEX.md#T-2:
  // it requires (a) an `openDocument` setter in AppContext, and (b) a
  // backend command that resolves a search-result id to a file path.
  // Until both ship, do not add a partial handler — leave the toast.
  const handleSourceClick = () => {
    showToast(t('search.pdfJumpComingSoon'), 'info')
  }

  return (
    <Card hoverable>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '8px',
        marginBottom: '6px',
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          minWidth: 0,
        }}>
          <FileTextIcon size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
          <button
            type="button"
            onClick={handleSourceClick}
            title={result.sourcePath || result.source}
            style={{
              fontSize: '12px',
              fontWeight: 500,
              color: 'var(--accent)',
              background: 'transparent',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              textAlign: 'left',
              textOverflow: 'ellipsis',
              overflow: 'hidden',
              whiteSpace: 'nowrap',
              maxWidth: '320px',
              textDecoration: 'underline',
              textDecorationStyle: 'dotted',
              textUnderlineOffset: '3px',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.textDecorationStyle = 'solid'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.textDecorationStyle = 'dotted'
            }}
          >
            {result.source.split(/[/\\]/).pop()}
          </button>
          {pageText && (
            <Badge variant="info" dot>
              {pageText}
            </Badge>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
          <span title={t(BAND_LABEL[band])}>
            <Badge variant={variant} dot>
              {scoreLabel}
            </Badge>
          </span>
        </div>
      </div>
      <div style={{
        fontSize: '14px',
        fontWeight: 600,
        color: 'var(--text-primary)',
        marginBottom: '6px',
      }}>
        {result.title}
      </div>
      <BodyText size="md" style={{ lineHeight: 1.65, color: 'var(--text-secondary)' }}>
        {result.snippet}
      </BodyText>
      {result.tags.length > 0 && (
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '6px',
          marginTop: '10px',
        }}>
          {result.tags.map(tag => (
            <Badge key={tag} variant="info">
              {tag}
            </Badge>
          ))}
        </div>
      )}
    </Card>
  )
}
