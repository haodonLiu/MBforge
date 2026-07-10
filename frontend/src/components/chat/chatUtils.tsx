import katex from 'katex'

/** Render inline LaTeX ($...$) within React children */
export function renderInlineLatex(children: React.ReactNode): React.ReactNode {
  if (typeof children === 'string') {
    const parts: React.ReactNode[] = []
    const regex = /(\$[^$\n]+?\$)/g
    let lastIndex = 0
    let match: RegExpExecArray | null
    while ((match = regex.exec(children)) !== null) {
      if (match.index > lastIndex) {
        parts.push(children.slice(lastIndex, match.index))
      }
      const formula = match[0].slice(1, -1).trim()
      if (formula) {
        try {
          const html = katex.renderToString(formula, { throwOnError: false, trust: false })
          parts.push(
            <span key={match.index} dangerouslySetInnerHTML={{ __html: html }} />
          )
        } catch {
          parts.push(<code key={match.index}>{formula}</code>)
        }
      }
      lastIndex = match.index + match[0].length
    }
    if (lastIndex < children.length) {
      parts.push(children.slice(lastIndex))
    }
    return parts.length > 0 ? <>{parts}</> : children
  }
  if (Array.isArray(children)) {
    return children.map((child: React.ReactNode, i: number) => (
      <span key={i}>{renderInlineLatex(child)}</span>
    ))
  }
  return children
}

/** 判断字符串是否为合法 SMILES */
export function isSmiles(s: string): boolean {
  if (!s || s.length < 2 || s.length > 200) return false
  return /^[A-Za-z0-9@+\-[\]()\\/#%=.:]+$/.test(s.trim())
}

/** SMILES → PubChem 图片 URL */
export function smilesToImgUrl(smiles: string): string {
  return `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/${encodeURIComponent(smiles)}/PNG?image_size=300x300`
}
