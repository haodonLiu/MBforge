import { useState, useRef, useEffect, useCallback } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import 'katex/dist/katex.min.css'
import { showToast } from '../hooks/useToast'

import {
  agentInit,
  agentCreateSession,
  agentChatStream,
  agentGetHistory,
  agentDestroySession,
  listDocumentsTauri,
  moleculeStatsTauri,
} from '../api/tauri'

import { useAppContext } from '../context/AppContext'
import { PageContainer } from '../components/ui/'
import ChatContextChip from './ChatContextChip'
import ChatMessage, { type LocalMessage } from './chat/ChatMessage'
import ChatTypingIndicator from './chat/ChatTypingIndicator'
import ChatInput from './chat/ChatInput'

import { FolderIcon, FileTextIcon, FlaskIcon } from './icons'

export default function Chat() {
  const { projectRoot } = useAppContext()
  const sessionIdRef = useRef<string>('')
  const [messages, setMessages] = useState<LocalMessage[]>([
    { role: 'assistant', content: '你好！我是 MBForge AI 助手。有什么关于分子或文献的问题可以问我。' },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [docCount, setDocCount] = useState(0)
  const [molCount, setMolCount] = useState(0)

  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => messagesContainerRef.current,
    estimateSize: () => 120,
    measureElement: (el) => el.getBoundingClientRect().height,
    overscan: 5,
  })

  const isNearBottom = () => {
    const el = messagesContainerRef.current
    if (!el) return true
    return el.scrollHeight - el.scrollTop - el.clientHeight < 100
  }

  const scrollToBottom = () => {
    virtualizer.scrollToIndex(messages.length - 1, { align: 'end', behavior: 'smooth' })
  }

  // Initialize Tauri agent on mount + load history
  useEffect(() => {
    const initAgent = async () => {
      const sid = crypto.randomUUID()
      sessionIdRef.current = sid

      try {
        await agentInit('http://127.0.0.1:18792')
        await agentCreateSession(sid, projectRoot ?? undefined)

        const history = await agentGetHistory(sid)
        if (history.length > 0) {
          setMessages(history.map(m => ({
            role: m.role as 'user' | 'assistant',
            content: m.content,
          })))
        }
      } catch (e) {
        showToast(`Agent 初始化失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
        console.error('Agent init failed:', e)
      }
    }

    initAgent()

    return () => {
      if (sessionIdRef.current) {
        agentDestroySession(sessionIdRef.current).catch(() => {})
      }
    }
  }, [projectRoot])

  useEffect(() => {
    if (isNearBottom()) scrollToBottom()
  }, [messages])

  useEffect(() => {
    if (!projectRoot) return
    listDocumentsTauri(projectRoot).then(resp => {
      if (resp.success) setDocCount(resp.documents.length)
    }).catch(() => {})
    moleculeStatsTauri(projectRoot).then(resp => {
      if (resp.success) setMolCount(resp.stats.total || 0)
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
      if (sessionIdRef.current) {
        await agentChatStream(
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
          () => { if (!settled) settled = true },
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

  return (
    <PageContainer>
      {/* 上下文信息 — 顶部 */}
      <div style={{ display: 'flex', gap: '16px', flexShrink: 0 }}>
        <ChatContextChip icon={<FolderIcon size={14} />} label={projectRoot ? projectRoot.split('/').pop() || projectRoot : '未选择项目'} />
        <ChatContextChip icon={<FileTextIcon size={14} />} label={`${docCount} 篇文献`} />
        <ChatContextChip icon={<FlaskIcon size={14} />} label={`${molCount} 个分子`} />
      </div>

      {/* 消息区域 */}
      <div ref={messagesContainerRef} className="chat-messages">
        <div className="chat-virtual-list" style={{ height: `${virtualizer.getTotalSize()}px` }}>
          {virtualizer.getVirtualItems().map((virtualItem) => {
            const msg = messages[virtualItem.index]
            return (
              <div
                key={msg.id ?? virtualItem.index}
                ref={virtualizer.measureElement}
                data-index={virtualItem.index}
                className="chat-virtual-item"
                style={{ transform: `translateY(${virtualItem.start}px)` }}
              >
                <ChatMessage msg={msg} />
              </div>
            )
          })}
        </div>
        {isLoading && <ChatTypingIndicator />}
      </div>

      {/* 快捷操作 + 输入框 — 底部 */}
      <ChatInput
        input={input}
        onInputChange={setInput}
        onSend={sendMessage}
        isLoading={isLoading}
        projectRoot={projectRoot}
      />
    </PageContainer>
  )
}
