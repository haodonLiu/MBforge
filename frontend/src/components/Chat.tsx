import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { listDocuments, moleculeStats, chatStream } from '../api/client'
import {
  isTauriAvailable,
  agentInit,
  agentCreateSession,
  agentChatStream,
  agentGetHistory,
  agentDestroySession,
} from '../api/tauri-bridge'
import type { ChatMessage } from '../api/tauri-bridge'
import { SendIcon, UserIcon, BotIcon, FolderIcon, FileTextIcon, FlaskIcon } from './icons'
import { getProjectRoot } from '../hooks/useProjectRoot'
import { Avatar, TextArea, IconButton, Button, PageContainer } from '../components/ui/'

/** Render inline LaTeX ($...$) within React children */
function renderInlineLatex(children: React.ReactNode): React.ReactNode {
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
          const html = katex.renderToString(formula, { throwOnError: false, trust: true })
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
    return children.map((child, i) => (
      <span key={i}>{renderInlineLatex(child)}</span>
    ))
  }
  return children
}

/** 判断字符串是否为合法 SMILES */
function isSmiles(s: string): boolean {
  if (!s || s.length < 2 || s.length > 200) return false
  return /^[A-Za-z0-9@+\-\[\]()\\/#%=.:]+$/.test(s.trim())
}

/** SMILES → PubChem 图片 URL */
function smilesToImgUrl(smiles: string): string {
  return `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/${encodeURIComponent(smiles)}/PNG?image_size=300x300`
}

interface LocalMessage {
  id?: string
  role: 'user' | 'assistant'
  content: string
}

export default function Chat() {
  const projectRoot = getProjectRoot()
  const sessionIdRef = useRef<string>('')
  const [messages, setMessages] = useState<LocalMessage[]>([
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

  // Initialize Tauri agent on mount
  useEffect(() => {
    if (!isTauriAvailable()) return

    const initAgent = async () => {
      const sid = crypto.randomUUID()
      sessionIdRef.current = sid

      // Load saved LLM config from localStorage (set by Settings)
      const savedConfig = localStorage.getItem('mbforge_llm_config')
      const config = savedConfig
        ? JSON.parse(savedConfig)
        : { provider: 'openai_compatible', base_url: 'http://localhost:8000/v1', api_key: '', model_name: 'default', max_tokens: 4096, temperature: 0.7, top_p: 0.9 }

      await agentInit(config, 'http://127.0.0.1:18792')
      await agentCreateSession(sid, projectRoot ?? undefined)
    }

    initAgent().catch(console.error)

    return () => {
      // Cleanup session on unmount
      if (sessionIdRef.current) {
        agentDestroySession(sessionIdRef.current).catch(() => {})
      }
    }
  }, [projectRoot])

  // Load agent history when session is ready
  useEffect(() => {
    if (!sessionIdRef.current || !isTauriAvailable()) return

    agentGetHistory(sessionIdRef.current)
      .then((history: ChatMessage[]) => {
        if (history.length > 0) {
          setMessages(history.map(m => ({
            role: m.role as 'user' | 'assistant',
            content: m.content,
          })))
        }
      })
      .catch(() => {})
  }, [sessionIdRef.current])

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

    const allMessages = [...messages, { role: 'user' as const, content: userMsg }]
    setMessages(allMessages)

    const assistantMsgId = Date.now().toString()
    setMessages(prev => [...prev, { id: assistantMsgId, role: 'assistant', content: '' }])

    let fullContent = ''
    let settled = false

    try {
      if (isTauriAvailable() && sessionIdRef.current) {
        const cancel = await agentChatStream(
          sessionIdRef.current,
          userMsg,
          (delta) => {
            fullContent += delta
            setMessages(prev =>
              prev.map(m => m.id === assistantMsgId
                ? { ...m, content: fullContent }
                : m
              )
            )
          },
          () => {
            if (!settled) {
              settled = true
            }
          },
          (error) => {
            if (!settled) {
              settled = true
              setMessages(prev =>
                prev.map(m => m.id === assistantMsgId
                  ? { ...m, content: `错误: ${error}` }
                  : m
                )
              )
            }
          },
        )
        // Store cancel for cleanup if needed
        ;(sendMessage as any)._cancel = cancel
      } else {
        // Browser dev mode fallback: use HTTP chatStream
        const chatMessages = allMessages.map(m => ({ role: m.role, content: m.content }))
        const cancel = chatStream(
          chatMessages,
          (event) => {
            if (event.error) {
              if (!settled) {
                settled = true
                setMessages(prev =>
                  prev.map(m => m.id === assistantMsgId
                    ? { ...m, content: `错误: ${event.error}` }
                    : m
                  )
                )
              }
            } else {
              fullContent += event.delta
              setMessages(prev =>
                prev.map(m => m.id === assistantMsgId
                  ? { ...m, content: fullContent }
                  : m
                )
              )
              if (event.finish_reason) {
                if (!settled) {
                  settled = true
                }
              }
            }
          },
        )
        ;(sendMessage as any)._cancel = cancel
      }
    } catch (e) {
      if (!settled) {
        setMessages(prev =>
          prev.map(m => m.id === assistantMsgId
            ? { ...m, content: `网络错误: ${e instanceof Error ? e.message : String(e)}` }
            : m
          )
        )
      }
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
    <PageContainer>
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
        <AnimatePresence initial={false}>
          {messages.map((msg, i) => (
            <motion.div
              key={msg.id ?? i}
              initial={{ opacity: 0, y: 12, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              style={{
                display: 'flex',
                gap: '10px',
                maxWidth: '88%',
                alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}
            >
              {msg.role === 'assistant' && (
                <div style={{ flexShrink: 0, marginTop: '4px' }}>
                  <Avatar size={32} variant="bot">
                    <BotIcon size={16} />
                  </Avatar>
                </div>
              )}
              <div style={{
                position: 'relative',
                padding: '14px 18px',
                background: msg.role === 'user'
                  ? 'linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 80%, #000))'
                  : 'var(--bg-surface)',
                color: msg.role === 'user' ? '#fff' : 'var(--text-primary)',
                borderRadius: msg.role === 'user' ? '18px 18px 4px 18px' : '4px 18px 18px 18px',
                boxShadow: msg.role === 'user'
                  ? '0 4px 12px rgba(0,0,0,0.15)'
                  : '0 2px 8px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
                border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                lineHeight: 1.65,
                fontSize: '14px',
              }}>
                {msg.role === 'assistant' ? (
                  <div className="chat-markdown" style={{
                    '--chat-code-bg': 'var(--bg-hover)',
                  } as React.CSSProperties}>
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        p: ({ children }) => {
                          const processed = renderInlineLatex(children)
                          return <p style={{ margin: '8px 0', '&:first-child': { marginTop: 0 } } as React.CSSProperties}>{processed}</p>
                        },
                        img: ({ node, ...props }) => (
                          <img
                            {...props}
                            style={{ maxWidth: '100%', borderRadius: '8px', margin: '8px 0', cursor: 'pointer' }}
                            onClick={() => props.src && window.open(props.src, '_blank')}
                          />
                        ),
                        code: ({ node, className, children, ...props }) => {
                          const text = String(children).trim()
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
                          const isBlock = className?.startsWith('language-')
                          if (isBlock) {
                            return (
                              <div style={{
                                background: 'var(--bg-hover)',
                                borderRadius: '10px',
                                padding: '14px 16px',
                                margin: '8px 0',
                                overflowX: 'auto',
                                fontSize: '13px',
                                border: '1px solid var(--border)',
                              }}>
                                <code className={className} {...props}>{children}</code>
                              </div>
                            )
                          }
                          return (
                            <code className={className} {...props}
                              style={{
                                background: 'var(--bg-hover)',
                                padding: '2px 6px',
                                borderRadius: '4px',
                                fontSize: '13px',
                              }}
                            >{children}</code>
                          )
                        },
                        ul: ({ children }) => <ul style={{ paddingLeft: '20px', margin: '6px 0' }}>{children}</ul>,
                        ol: ({ children }) => <ol style={{ paddingLeft: '20px', margin: '6px 0' }}>{children}</ol>,
                        table: ({ children }) => (
                          <div style={{ overflowX: 'auto', margin: '8px 0' }}>
                            <table style={{ borderCollapse: 'collapse', fontSize: '13px', width: '100%' }}>
                              {children}
                            </table>
                          </div>
                        ),
                        th: ({ children }) => <th style={{ border: '1px solid var(--border)', padding: '6px 10px', background: 'var(--bg-hover)', textAlign: 'left' }}>{children}</th>,
                        td: ({ children }) => <td style={{ border: '1px solid var(--border)', padding: '6px 10px' }}>{children}</td>,
                        h1: ({ children }) => <h1 style={{ fontSize: '16px', fontWeight: 600, margin: '12px 0 6px' }}>{children}</h1>,
                        h2: ({ children }) => <h2 style={{ fontSize: '15px', fontWeight: 600, margin: '10px 0 5px' }}>{children}</h2>,
                        h3: ({ children }) => <h3 style={{ fontSize: '14px', fontWeight: 600, margin: '8px 0 4px' }}>{children}</h3>,
                        blockquote: ({ children }) => (
                          <blockquote style={{
                            margin: '8px 0',
                            padding: '6px 12px',
                            borderLeft: '3px solid var(--accent)',
                            background: 'var(--bg-hover)',
                            borderRadius: '0 6px 6px 0',
                            color: 'var(--text-secondary)',
                          }}>{children}</blockquote>
                        ),
                        hr: () => <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '12px 0' }} />,
                      }}
                    >{msg.content}</ReactMarkdown>
                  </div>
                ) : (
                  <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
                )}
              </div>
              {msg.role === 'user' && (
                <div style={{ flexShrink: 0, marginTop: '4px' }}>
                  <Avatar size={32} variant="user">
                    <UserIcon size={16} />
                  </Avatar>
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
        {isLoading && (
          <div style={{ display: 'flex', gap: '10px', maxWidth: '88%', alignSelf: 'flex-start' }}>
            <div style={{ flexShrink: 0, marginTop: '4px' }}>
              <Avatar size={32} variant="bot">
                <BotIcon size={16} />
              </Avatar>
            </div>
            <div style={{
              padding: '16px 20px',
              background: 'var(--bg-surface)',
              borderRadius: '4px 18px 18px 18px',
              border: '1px solid var(--border)',
              boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
              display: 'flex',
              gap: '5px',
              alignItems: 'center',
            }}>
              {[0, 1, 2].map(i => (
                <motion.div
                  key={i}
                  style={{
                    width: '7px', height: '7px',
                    background: 'var(--text-muted)',
                    borderRadius: '50%',
                  }}
                  animate={{ y: [0, -6, 0], opacity: [0.5, 1, 0.5] }}
                  transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15, ease: 'easeInOut' }}
                />
              ))}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 快捷操作 + 输入框 — 底部 */}
      <div style={{ flexShrink: 0 }}>
        <div style={{
          display: 'flex', gap: '8px', marginBottom: '10px', flexWrap: 'wrap',
        }}>
          <Button variant="ghost" size="sm" onClick={() => insertTemplate('search_mol')}><FlaskIcon size={13} /> 搜索分子</Button>
          <Button variant="ghost" size="sm" onClick={() => insertTemplate('analyze_sar')}><FlaskIcon size={13} /> SAR 分析</Button>
          <Button variant="ghost" size="sm" onClick={() => insertTemplate('dock')}><FlaskIcon size={13} /> 分子对接</Button>
        </div>

        <div style={{
          display: 'flex', gap: '12px', padding: '12px 16px',
          background: 'var(--bg-surface)', borderRadius: '12px',
          border: '1px solid var(--border)',
        }}>
          <TextArea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={projectRoot ? "输入问题... (Enter 发送, Shift+Enter 换行)" : "请先打开一个项目"}
            maxHeight="120px"
            disabled={isLoading || !projectRoot}
            rows={1}
          />
          <IconButton
            size={36}
            disabled={!input.trim() || isLoading || !projectRoot}
            onClick={sendMessage}
          >
            <SendIcon size={16} />
          </IconButton>
        </div>
      </div>
    </PageContainer>
  )
}

function ContextChip({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      style={{
        display: 'flex', alignItems: 'center', gap: '6px',
        padding: '6px 12px', background: 'var(--bg-surface)',
        border: '1px solid var(--border)', borderRadius: '20px',
        fontSize: '12px', color: 'var(--text-secondary)',
      }}
    >
      <span style={{ color: 'var(--text-muted)' }}>{icon}</span>
      <span>{label}</span>
    </motion.div>
  )
}


