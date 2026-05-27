import { useState, useRef, useEffect, useCallback } from 'react'
import { agentChat, chat } from '../api/client'
import { SendIcon, UserIcon, BotIcon, SearchIcon, BarChartIcon, TargetIcon, FolderIcon, FileTextIcon, FlaskIcon, GlobeIcon } from './icons'
import { getProjectRoot } from '../hooks/useProjectRoot'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

type ChatMode = 'global' | 'project'

export default function Chat() {
  const projectRoot = getProjectRoot()
  const [mode, setMode] = useState<ChatMode>(projectRoot ? 'project' : 'global')
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: '你好！我是 MBForge AI 助手。有什么关于分子或文献的问题可以问我。' },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    if (!projectRoot && mode === 'project') {
      setMode('global')
    }
  }, [projectRoot, mode])

  const sendMessage = useCallback(async () => {
    if (!input.trim() || isLoading) return

    const userMsg = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setIsLoading(true)

    const allMessages = [...messages, { role: 'user' as const, content: userMsg }]

    try {
      if (mode === 'global') {
        const resp = await chat(allMessages.map(m => ({ role: m.role, content: m.content })))
        setMessages(prev => [...prev, { role: 'assistant', content: resp.content }])
      } else {
        const resp = await agentChat(
          projectRoot,
          allMessages.map(m => ({ role: m.role, content: m.content })),
        )
        if (resp.success) {
          setMessages(prev => [...prev, { role: 'assistant', content: resp.content }])
        } else {
          setMessages(prev => [...prev, { role: 'assistant', content: `错误: ${resp.error || '未知错误'}` }])
        }
      }
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `网络错误: ${e instanceof Error ? e.message : String(e)}` }])
    } finally {
      setIsLoading(false)
    }
  }, [input, isLoading, messages, mode, projectRoot])

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
      display: 'grid',
      gridTemplateColumns: '1fr 300px',
      gap: '24px',
      height: '100%',
      padding: '24px',
    }}>
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--bg-surface)',
        borderRadius: '16px',
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '12px 16px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}>
          <div style={{
            display: 'flex',
            background: 'var(--bg-base)',
            borderRadius: '8px',
            padding: '3px',
            border: '1px solid var(--border)',
          }}>
            <button
              onClick={() => setMode('global')}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                border: 'none',
                cursor: 'pointer',
                fontSize: '12px',
                fontWeight: 500,
                background: mode === 'global' ? 'var(--accent)' : 'transparent',
                color: mode === 'global' ? 'white' : 'var(--text-secondary)',
                transition: 'all 0.15s',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <GlobeIcon size={14} />
              全局
            </button>
            <button
              onClick={() => projectRoot && setMode('project')}
              disabled={!projectRoot}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                border: 'none',
                cursor: projectRoot ? 'pointer' : 'not-allowed',
                fontSize: '12px',
                fontWeight: 500,
                background: mode === 'project' ? 'var(--accent)' : 'transparent',
                color: mode === 'project' ? 'white' : projectRoot ? 'var(--text-secondary)' : 'var(--text-muted)',
                transition: 'all 0.15s',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                opacity: projectRoot ? 1 : 0.5,
              }}
            >
              <FolderIcon size={14} />
              项目
            </button>
          </div>
          {mode === 'global' && (
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              全局模式 - 直接与 LLM 对话
            </span>
          )}
          {mode === 'project' && projectRoot && (
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              项目模式 - 基于项目知识库
            </span>
          )}
        </div>
        <div style={{
          flex: 1,
          padding: '24px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px',
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
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: 'var(--accent)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  color: 'white',
                }}>
                  <BotIcon size={16} />
                </div>
              )}
              <div style={{
                padding: '12px 16px',
                background: msg.role === 'user' ? 'var(--accent)' : 'var(--bg-base)',
                color: msg.role === 'user' ? 'white' : 'var(--text-primary)',
                borderRadius: '12px',
                border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                lineHeight: 1.6,
                fontSize: '14px',
                whiteSpace: 'pre-wrap',
              }}>
                {msg.content}
              </div>
              {msg.role === 'user' && (
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: 'var(--bg-hover)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <UserIcon size={16} />
                </div>
              )}
            </div>
          ))}
          {isLoading && (
            <div style={{
              display: 'flex',
              gap: '12px',
              maxWidth: '85%',
            }}>
              <div style={{
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                background: 'var(--accent)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                color: 'white',
              }}>
                <BotIcon size={16} />
              </div>
              <div style={{
                padding: '12px 16px',
                background: 'var(--bg-base)',
                borderRadius: '12px',
                border: '1px solid var(--border)',
              }}>
                <span style={{
                  display: 'inline-block',
                  width: '8px',
                  height: '8px',
                  background: 'var(--text-muted)',
                  borderRadius: '50%',
                  animation: 'pulse 1.4s infinite',
                }} />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div style={{
          padding: '16px 20px',
          borderTop: '1px solid var(--border)',
        }}>
          <div style={{
            display: 'flex',
            gap: '12px',
            padding: '12px 16px',
            background: 'var(--bg-base)',
            borderRadius: '12px',
            border: '1px solid var(--border)',
          }}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入问题... (Enter 发送, Shift+Enter 换行)"
              disabled={isLoading}
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                outline: 'none',
                fontSize: '14px',
                color: 'var(--text-primary)',
                resize: 'none',
                maxHeight: '120px',
                fontFamily: 'inherit',
                lineHeight: 1.5,
              }}
              rows={1}
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || isLoading}
              style={{
                width: '36px',
                height: '36px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: input.trim() && !isLoading ? 'var(--accent)' : 'var(--bg-hover)',
                color: input.trim() && !isLoading ? 'white' : 'var(--text-muted)',
                border: 'none',
                borderRadius: '8px',
                cursor: input.trim() && !isLoading ? 'pointer' : 'not-allowed',
                transition: 'all 0.2s',
                flexShrink: 0,
              }}
            >
              <SendIcon size={16} />
            </button>
          </div>
        </div>
      </div>

      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
      }}>
        <div style={{
          background: 'var(--bg-surface)',
          borderRadius: '12px',
          padding: '16px',
          border: '1px solid var(--border)',
        }}>
          <div style={{
            fontSize: '12px',
            fontWeight: 600,
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
            marginBottom: '12px',
          }}>
            当前上下文
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <ContextItem
              icon={mode === 'global' ? <GlobeIcon size={16} /> : <FolderIcon size={16} />}
              label={mode === 'global' ? '全局模式' : (projectRoot ? projectRoot.split('/').pop() || projectRoot : '未选择项目')}
            />
            <ContextItem icon={<FileTextIcon size={16} />} label="42 篇已索引文献" />
            <ContextItem icon={<FlaskIcon size={16} />} label="128 个分子" />
          </div>
        </div>

        <div style={{
          background: 'var(--bg-surface)',
          borderRadius: '12px',
          padding: '16px',
          border: '1px solid var(--border)',
        }}>
          <div style={{
            fontSize: '12px',
            fontWeight: 600,
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
            marginBottom: '12px',
          }}>
            快捷操作
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <ContextItem
              icon={<SearchIcon size={16} />}
              label="搜索分子"
              onClick={() => insertTemplate('search_mol')}
            />
            <ContextItem
              icon={<BarChartIcon size={16} />}
              label="SAR 分析"
              onClick={() => insertTemplate('analyze_sar')}
            />
            <ContextItem
              icon={<TargetIcon size={16} />}
              label="分子对接"
              onClick={() => insertTemplate('dock')}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

function ContextItem({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick?: () => void }) {
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '8px 10px',
        borderRadius: '6px',
        cursor: onClick ? 'pointer' : 'default',
        color: 'var(--text-secondary)',
        fontSize: '13px',
        transition: 'all 0.15s',
      }}
      onMouseEnter={e => {
        if (onClick) {
          e.currentTarget.style.background = 'var(--bg-hover)'
          e.currentTarget.style.color = 'var(--text-primary)'
        }
      }}
      onMouseLeave={e => {
        if (onClick) {
          e.currentTarget.style.background = 'transparent'
          e.currentTarget.style.color = 'var(--text-secondary)'
        }
      }}
    >
      <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{icon}</span>
      <span>{label}</span>
    </div>
  )
}
