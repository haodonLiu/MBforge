/** Shared markdown extension components for code blocks.

Used by `ChatMarkdown` (LLM chat surface) and `ReorganizedPane`
(document reorganized-md surface). Both surfaces need:
- Mermaid (`language-mermaid`) → lazy-loaded SVG via `MermaidCode`
- Inline SMILES → image (chat surface only)

The ReorganizedPane adds an `onMoleculeClick` callback so the user
can click a MoleCode diagram and jump to the corresponding PDF page.
The chat surface passes no callback (no-op).
*/

import { Suspense, lazy } from 'react'
import type { ReactNode } from 'react'
import { isSmiles, smilesToImgUrl } from './chatUtils'

const MermaidCode = lazy(() =>
  import('../ui/MermaidCode').then(m => ({ default: m.MermaidCode }))
)

export interface MoleculeClickInfo {
  /** 1-based page number (extracted from `%% page=N` mermaid comment). */
  page: number
}

interface CodeBlockProps {
  className?: string
  children?: ReactNode
  node?: unknown
  /** Called when the user clicks a Mermaid block. */
  onMoleculeClick?: (info: MoleculeClickInfo) => void
}

/** Parse `%% page=3` from the first line(s) of a mermaid block. */
function parseMermaidPage(code: string): number | null {
  for (const line of code.split('\n').slice(0, 3)) {
    const m = /%%\s*page\s*=\s*(\d+)/i.exec(line)
    if (m) return parseInt(m[1], 10)
  }
  return null
}

/**
 * Render a `<code>` block inside a Markdown document.
 *
 * - `language-mermaid` → Mermaid SVG (clickable if `onMoleculeClick` set)
 * - Bare SMILES in inline code → image render (chat-style)
 * - Other code blocks → plain wrapped `<code>`
 * - Inline code (no className) → `<code>` pass-through
 */
export function MermaidAwareCodeBlock({
  className,
  children,
  onMoleculeClick,
}: CodeBlockProps) {
  const text = String(children ?? '').trim()

  // Inline SMILES (chat only)
  if (!className && isSmiles(text)) {
    return (
      <span className="chat-smiles-inline">
        <img
          src={smilesToImgUrl(text)}
          alt={text}
          onClick={() => window.open(smilesToImgUrl(text), '_blank')}
          onError={e => {
            ;(e.target as HTMLImageElement).style.display = 'none'
          }}
        />
        <code className="chat-smiles-code">{text}</code>
      </span>
    )
  }

  // Mermaid / MoleCode block
  if (className === 'language-mermaid' || className === 'language-molecode') {
    const page = onMoleculeClick ? parseMermaidPage(text) : null
    return (
      <Suspense
        fallback={<div style={{ padding: 8, opacity: 0.6 }}>Loading diagram…</div>}
      >
        <div
          className="mermaid-block"
          data-page={page ?? undefined}
          onClick={
            page && onMoleculeClick
              ? () => onMoleculeClick({ page })
              : undefined
          }
          style={page && onMoleculeClick ? { cursor: 'pointer' } : undefined}
        >
          <MermaidCode code={text} />
        </div>
      </Suspense>
    )
  }

  // Other block-level code
  const isBlock = className?.startsWith('language-')
  if (isBlock) {
    return (
      <div className="chat-code-block">
        <code className={className}>{children}</code>
      </div>
    )
  }

  // Inline code
  return <code className="chat-inline-code">{children}</code>
}