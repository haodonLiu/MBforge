import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { fetchReorganizedMarkdown } from '@/api/http/library'
import { MermaidAwareCodeBlock } from '@/components/chat/markdownExtensions'
import Spinner from '@/components/ui/Spinner'

interface ReorganizedPaneProps {
  docId: string
  libraryRoot: string
  /** Called when user clicks a MoleCode mermaid block that has `%% page=N` metadata. */
  onMoleculeClick?: (info: { page: number }) => void
}

export default function ReorganizedPane({
  docId,
  libraryRoot,
  onMoleculeClick,
}: ReorganizedPaneProps) {
  const [md, setMd] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setMd(null)
    setError(null)
    void fetchReorganizedMarkdown(docId, libraryRoot).then(r => {
      if (cancelled) return
      if (r.ok) setMd(r.text)
      else setError(r.error)
    })
    return () => {
      cancelled = true
    }
  }, [docId, libraryRoot])

  if (error) {
    return (
      <div style={{ padding: 16, color: 'var(--danger)' }}>
        Failed to load reorganized markdown: {error}
      </div>
    )
  }
  if (md === null) {
    return (
      <div style={{ padding: 32, textAlign: 'center' }}>
        <Spinner /> Loading…
      </div>
    )
  }

  return (
    <div className="reorganized-pane markdown-preview" style={{ padding: '16px 24px', overflow: 'auto' }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code: props => (
            <MermaidAwareCodeBlock
              {...props}
              onMoleculeClick={onMoleculeClick}
            />
          ),
          img: ({ node: _node, ...props }) => (
            <img
              {...props}
              alt={props.alt || ''}
              style={{ maxWidth: '100%' }}
            />
          ),
        }}
      >
        {md}
      </ReactMarkdown>
    </div>
  )
}