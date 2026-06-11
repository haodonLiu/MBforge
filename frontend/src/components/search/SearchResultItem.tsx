import { FileTextIcon } from '../icons'
import Card from '../ui/Card'
import BodyText from '../ui/BodyText'
import Badge from '../ui/Badge'

export interface SearchResultItemData {
  id: string
  title: string
  snippet: string
  source: string
  tags: string[]
}

export interface SearchResultItemProps {
  result: SearchResultItemData
}

/**
 * 搜索结果单项组件。
 */
export default function SearchResultItem({ result }: SearchResultItemProps) {
  return (
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
          {result.source.split(/[/\\]/).pop()}
        </span>
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
