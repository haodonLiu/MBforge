import { useState, useRef, useEffect, useCallback } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import 'katex/dist/katex.min.css'
import { showToast } from '@/hooks/useToast'

import {
  agentInit,
  agentCreateSession,
  agentChatStream,
  agentGetHistory,
  agentDestroySession,
  listDocumentsTauri,
  moleculeStatsTauri,
} from '@/api/tauri'

import { useAppContext } from '@/context/AppContext'
import ChatContextChip from '@/components/ChatContextChip'
import ChatMessage, { type LocalMessage } from '@/components/chat/ChatMessage'
import ChatTypingIndicator from '@/components/chat/ChatTypingIndicator'
import ChatInput from '@/components/chat/ChatInput'

import { FolderIcon, FileTextIcon, FlaskIcon } from '@/components/icons'

interface ChatTabProps {
  initialQuery?: string
}

export default function ChatTab({ initialQuery = '' }: ChatTabProps) {
  const { projectRoot } = useAppContext()
  const sessionIdRef = useRef<string>('')
  const [messages, setMessages] = useState<LocalMessage[]>([
    { role: 'assistant', content: '你好！我是 MBForge AI 助手。有什么关于分子或文献的问题可以问我。' },
  ])
  const [input, setInput] = useState(initialQuery)
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

  useEffect(() => {
    const el = messagesContainerRef.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
      virtualizer.scrollToIndex(messages.length - 1, { align: 'end', behavior: 'smooth' })
    }
  }, [messages, virtualizer])

  useEffect(() => {
    const initAgent = async () => {
      const sid = crypto.randomUUID()
      sessionIdRef.current = sid

      try {
        await agentInit('http://127.0.0.1:18792')
        await agentCreateSession(sid, projectRoot)

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

    void initAgent()

    return () => {
      if (sessionIdRef.current) {
        agentDestroySession(sessionIdRef.current).catch(() => {})
      }
    }
  }, [projectRoot])

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
    } catch (e) {
      setMessages(prev =>
        prev.map(m => m.id === assistantMsgId
          ? { ...m, content: `网络错误: ${e instanceof Error ? e.message : String(e)}` }
          : m
        )
      )
    } finally {
      setIsLoading(false)
    }
  }, [input, isLoading, messages, projectRoot])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', gap: '16px', flexShrink: 0 }}>
        <ChatContextChip icon={<FolderIcon size={14} />} label={projectRoot ? projectRoot.split('/').pop() || projectRoot : '未选择项目'} />
        <ChatContextChip icon={<FileTextIcon size={14} />} label={`${docCount} 篇文献`} />
        <ChatContextChip icon={<FlaskIcon size={14} />} label={`${molCount} 个分子`} />
      </div>

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

      <ChatInput
        input={input}
        onInputChange={setInput}
        onSend={sendMessage}
        isLoading={isLoading}
        projectRoot={projectRoot}
      />
    </div>
  )
}
