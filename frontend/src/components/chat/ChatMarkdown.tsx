import { Suspense, lazy } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { renderInlineLatex, isSmiles, smilesToImgUrl } from './chatUtils'

const MermaidCode = lazy(() =>
  import('../ui/MermaidCode').then(m => ({ default: m.MermaidCode }))
)

interface ChatMarkdownProps {
  content: string
}

export default function ChatMarkdown({ content }: ChatMarkdownProps) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => {
            const processed = renderInlineLatex(children)
            return <p>{processed}</p>
          },
          img: ({ node, ...props }) => (
            <img
              {...props}
              alt={props.alt || ''}
              onClick={() => props.src && window.open(props.src, '_blank')}
            />
          ),
          code: ({ node, className, children, ...props }) => {
            const text = String(children).trim()
            if (!className && isSmiles(text)) {
              return (
                <span className="chat-smiles-inline">
                  <img
                    src={smilesToImgUrl(text)}
                    alt={text}
                    onClick={() => window.open(smilesToImgUrl(text), '_blank')}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                  <code className="chat-smiles-code">{text}</code>
                </span>
              )
            }
            if (className === 'language-mermaid') {
              return (
                <Suspense fallback={<div>Loading diagram...</div>}>
                  <MermaidCode code={text} />
                </Suspense>
              )
            }
            const isBlock = className?.startsWith('language-')
            if (isBlock) {
              return (
                <div className="chat-code-block">
                  <code className={className} {...props}>{children}</code>
                </div>
              )
            }
            return (
              <code className="chat-inline-code" {...props}>{children}</code>
            )
          },
        }}
      >{content}</ReactMarkdown>
    </div>
  )
}
