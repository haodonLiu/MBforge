import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

interface Props {
  formula: string
  displayMode?: boolean
  className?: string
}

export default function Latex({ formula, displayMode = false, className }: Props) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(formula, {
        displayMode,
        throwOnError: false,
        trust: true,
      })
    } catch {
      return `<code>${formula}</code>`
    }
  }, [formula, displayMode])

  return (
    <span
      className={className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
