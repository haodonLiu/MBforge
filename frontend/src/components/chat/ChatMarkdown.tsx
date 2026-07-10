import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { renderInlineLatex } from './chatUtils'
import { MermaidAwareCodeBlock } from './markdownExtensions'

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
          code: props => <MermaidAwareCodeBlock {...props} />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}