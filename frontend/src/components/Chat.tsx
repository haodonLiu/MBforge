import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { agentChat, getChatHistory, listDocuments, moleculeStats } from '../api/client'
import { SendIcon, UserIcon, BotIcon, FolderIcon, FileTextIcon, FlaskIcon } from './icons'
import { getProjectRoot } from '../hooks/useProjectRoot'

/** 判断字符串是否为合法 SMILES */
function isSmiles(s: string): boolean {
  if (!s || s.length < 2 || s.length > 200) return false
  // SMILES 只含化学符号：字母、数字、括号、键符号等
  return /^[A-Za-z0-9@+\-\[\]()\\/#%=.:]+$/.test(s.trim())
}

/** SMILES → PubChem 图片 URL */
function smilesToImgUrl(smiles: string): string {
  return `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/${encodeURIComponent(smiles)}/PNG?image_size=300x300`
}

interface ChatMessage {
  id?: string
  role: 'user' | 'assistant'
  content: string
}

export default function Chat() {
  const projectRoot = getProjectRoot()
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: '你好！我是 MBForge AI 助手。有什么关于分子或文献的问题可以问我。' },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [docCount, setDocCount] = useState(0)
  const [molCount, setMolCount] = useState(0)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    if (!projectRoot) return
    getChatHistory(projectRoot).then(resp => {
      if (resp.success && resp.messages && resp.messages.length > 0) {
        setMessages(resp.messages.map(m => ({
          id: m.id,
          role: m.role as 'user' | 'assistant',
          content: m.content,
        })))
      }
    }).catch(() => {})
  }, [projectRoot])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    if (!projectRoot) return
    listDocuments(projectRoot).then(resp => {
      if (resp.success) setDocCount(resp.documents.length)
    }).catch(() => {})
    moleculeStats(projectRoot).then(resp => {
      if (resp.success) setMolCount((resp.stats as any).total || 0)
    }).catch(() => {})
  }, [projectRoot])

  const sendMessage = useCallback(async () => {
    if (!input.trim() || isLoading || !projectRoot) return

    const userMsg = input.trim()
    setInput('')
    setIsLoading(true)

    // 构造完整消息列表：历史 + 新用户消息
    const allMessages = [...messages, { role: 'user' as const, content: userMsg }]
    setMessages(allMessages)

    try {
      const resp = await agentChat(
        projectRoot,
        allMessages.map(m => ({ role: m.role, content: m.content })),
      )
      if (resp.success) {
        setMessages(prev => [...prev, { role: 'assistant', content: resp.content }])
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: `错误: ${resp.error || '未知错误'}` }])
      }
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `网络错误: ${e instanceof Error ? e.message : String(e)}` }])
    } finally {
      setIsLoading(false)
    }
  }, [input, isLoading, messages, projectRoot])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const insertTemplate = (template: string) => {
    const templates: Record<string, string> = {
      search_mol: '搜索分子：',
      analyze_sar: '请分析这些分子的SAR关系：',
      dock: '执行分子对接：',
    }
    setInput(prev => prev + (templates[template] || ''))
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      padding: '24px',
      gap: '16px',
    }}>
      {/* 上下文信息 — 顶部 */}
      <div style={{
        display: 'flex',
        gap: '16px',
        flexShrink: 0,
      }}>
        <ContextChip icon={<FolderIcon size={14} />} label={projectRoot ? projectRoot.split('/').pop() || projectRoot : '未选择项目'} />
        <ContextChip icon={<FileTextIcon size={14} />} label={`${docCount} 篇文献`} />
        <ContextChip icon={<FlaskIcon size={14} />} label={`${molCount} 个分子`} />
      </div>

      {/* 消息区域 */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        padding: '8px 0',
      }}>
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              gap: '12px',
              maxWidth: '85%',
              alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
              animation: 'messageIn 0.3s ease-out',
            }}
          >
            {msg.role === 'assistant' && (
              <div style={{
                width: '32px', height: '32px', borderRadius: '50%',
                background: 'var(--accent)', display: 'flex', alignItems: 'center',
                justifyContent: 'center', flexShrink: 0, color: 'white',
              }}>
                <BotIcon size={16} />
              </div>
            )}
            <div style={{
              padding: '12px 16px',
              background: msg.role === 'user' ? 'var(--accent)' : 'var(--bg-surface)',
              color: msg.role === 'user' ? 'white' : 'var(--text-primary)',
              borderRadius: '12px',
              border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
              lineHeight: 1.6, fontSize: '14px', maxWidth: '85%',
            }}>
              {msg.role === 'assistant' ? (
                <div className="chat-markdown">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      img: ({ node, ...props }) => (
                        <img
                          {...props}
                          style={{ maxWidth: '100%', borderRadius: '8px', margin: '8px 0', cursor: 'pointer' }}
                          onClick={() => props.src && window.open(props.src, '_blank')}
                        />
                      ),
                      code: ({ node, className, children, ...props }) => {
                        const text = String(children).trim()
                        // 行内代码：检测 SMILES
                        if (!className && isSmiles(text)) {
                          return (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', verticalAlign: 'middle' }}>
                              <img
                                src={smilesToImgUrl(text)}
                                alt={text}
                                style={{ height: '32px', borderRadius: '4px', cursor: 'pointer' }}
                                onClick={() => window.open(smilesToImgUrl(text), '_blank')}
                                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                              />
                              <code style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{text}</code>
                            </span>
                          )
                        }
                        return <code className={className} {...props}>{children}</code>
                      },
                    }}
                  >{msg.content}</ReactMarkdown>
                </div>
              ) : (
                <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
              )}
            </div>
            {msg.role === 'user' && (
              <div style={{
                width: '32px', height: '32px', borderRadius: '50%',
                background: 'var(--bg-hover)', display: 'flex', alignItems: 'center',
                justifyContent: 'center', flexShrink: 0,
              }}>
                <UserIcon size={16} />
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div style={{ display: 'flex', gap: '12px', maxWidth: '85%' }}>
            <div style={{
              width: '32px', height: '32px', borderRadius: '50%',
              background: 'var(--accent)', display: 'flex', alignItems: 'center',
              justifyContent: 'center', flexShrink: 0, color: 'white',
            }}>
              <BotIcon size={16} />
            </div>
            <div style={{
              padding: '12px 16px', background: 'var(--bg-surface)',
              borderRadius: '12px', border: '1px solid var(--border)',
            }}>
              <span style={{
                display: 'inline-block', width: '8px', height: '8px',
                background: 'var(--text-muted)', borderRadius: '50%',
                animation: 'pulse 1.4s infinite',
              }} />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 快捷操作 + 输入框 — 底部 */}
      <div style={{ flexShrink: 0 }}>
        {/* 快捷操作 */}
        <div style={{
          display: 'flex', gap: '8px', marginBottom: '10px', flexWrap: 'wrap',
        }}>
          <QuickAction icon={<FlaskIcon size={13} />} label="搜索分子" onClick={() => insertTemplate('search_mol')} />
          <QuickAction icon={<FlaskIcon size={13} />} label="SAR 分析" onClick={() => insertTemplate('analyze_sar')} />
          <QuickAction icon={<FlaskIcon size={13} />} label="分子对接" onClick={() => insertTemplate('dock')} />
        </div>

        {/* 输入框 */}
        <div style={{
          display: 'flex', gap: '12px', padding: '12px 16px',
          background: 'var(--bg-surface)', borderRadius: '12px',
          border: '1px solid var(--border)',
        }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={projectRoot ? "输入问题... (Enter 发送, Shift+Enter 换行)" : "请先打开一个项目"}
            disabled={isLoading || !projectRoot}
            style={{
              flex: 1, background: 'transparent', border: 'none', outline: 'none',
              fontSize: '14px', color: 'var(--text-primary)', resize: 'none',
              maxHeight: '120px', fontFamily: 'inherit', lineHeight: 1.5,
            }}
            rows={1}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
            style={{
              width: '36px', height: '36px', display: 'flex', alignItems: 'center',
              justifyContent: 'center',
              background: input.trim() && !isLoading ? 'var(--accent)' : 'var(--bg-hover)',
              color: input.trim() && !isLoading ? 'white' : 'var(--text-muted)',
              border: 'none', borderRadius: '8px',
              cursor: input.trim() && !isLoading ? 'pointer' : 'not-allowed',
              transition: 'all 0.2s', flexShrink: 0,
            }}
          >
            <SendIcon size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}

function ContextChip({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '6px',
      padding: '6px 12px', background: 'var(--bg-surface)',
      border: '1px solid var(--border)', borderRadius: '20px',
      fontSize: '12px', color: 'var(--text-secondary)',
    }}>
      <span style={{ color: 'var(--text-muted)' }}>{icon}</span>
      <span>{label}</span>
    </div>
  )
}

function QuickAction({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: '5px',
        padding: '5px 12px', background: 'var(--bg-surface)',
        border: '1px solid var(--border)', borderRadius: '16px',
        fontSize: '12px', color: 'var(--text-secondary)',
        cursor: 'pointer', transition: 'all 0.15s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--accent)'
        e.currentTarget.style.color = 'var(--text-primary)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.color = 'var(--text-secondary)'
      }}
    >
      {icon} {label}
    </button>
  )
}
