import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

interface Props {
  text: string
  className?: string
}

/**
 * Parse text containing mixed content and LaTeX formulas.
 * Supports:
 *   Display: $$...$$ or \[...\]
 *   Inline: $...$ or \(...\)
 */
export default function LatexText({ text, className }: Props) {
  const parts = useMemo(() => parseLatex(text), [text])

  return (
    <span className={className}>
      {parts.map((part, i) =>
        part.type === 'latex' ? (
          <span
            key={i}
            dangerouslySetInnerHTML={{
              __html: katex.renderToString(part.content, {
                displayMode: part.display,
                throwOnError: false,
                trust: true,
              }),
            }}
          />
        ) : (
          <span key={i}>{part.content}</span>
        )
      )}
    </span>
  )
}

interface TextPart {
  type: 'text' | 'latex'
  content: string
  display?: boolean
}

function parseLatex(text: string): TextPart[] {
  const parts: TextPart[] = []
  // Match display math ($$...$$, \[...\]) and inline math ($...$, \(...\))
  const regex = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\$[^$\n]+?\$|\\\([^)]+?\\\))/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = regex.exec(text)) !== null) {
    // Add text before match
    if (match.index > lastIndex) {
      parts.push({ type: 'text', content: text.slice(lastIndex, match.index) })
    }

    const raw = match[0]
    const isDisplay = raw.startsWith('$$') || raw.startsWith('\\[')
    // Strip delimiters
    const formula = isDisplay
      ? raw.slice(2, -2).trim()
      : raw.slice(1, -1).trim()

    if (formula) {
      parts.push({ type: 'latex', content: formula, display: isDisplay })
    }
    lastIndex = match.index + raw.length
  }

  // Remaining text
  if (lastIndex < text.length) {
    parts.push({ type: 'text', content: text.slice(lastIndex) })
  }

  return parts
}
