import { useState, useRef, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
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
import { getSettings } from '@/api/tauri/settings'

import { useAppContext } from '@/context/AppContext'
import ChatContextChip from '@/components/ChatContextChip'
import ChatMessage, { type LocalMessage } from '@/components/chat/ChatMessage'
import ChatTypingIndicator from '@/components/chat/ChatTypingIndicator'
import ChatInput from '@/components/chat/ChatInput'

import { FolderIcon, FileTextIcon, FlaskIcon } from '@/components/icons'

interface ChatTabProps {
  query: string
  onQueryChange: (query: string) => void
}

const DEFAULT_SIDECAR_URL = 'http://127.0.0.1:18792'

export default function ChatTab({ query, onQueryChange }: ChatTabProps) {
  const { t } = useTranslation()
  const { projectRoot } = useAppContext()
  const sessionIdRef = useRef<string>('')
  const [messages, setMessages] = useState<LocalMessage[]>([
    { role: 'assistant', content: t('discover.chat.greeting') },
  ])
  const [input, setInput] = useState(query)
  const [isLoading, setIsLoading] = useState(false)
  const [docCount, setDocCount] = useState(0)
  const [molCount, setMolCount] = useState(0)
  const isSubmittingRef = useRef(false)

  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => messagesContainerRef.current,
    estimateSize: () => 120,
    measureElement: (el) => el.getBoundingClientRect().height,
    overscan: 5,
  })

  useEffect(() => {
    if (isSubmittingRef.current) {
      isSubmittingRef.current = false
      return
    }
    setInput(query)
  }, [query])

  useEffect(() => {
    const el = messagesContainerRef.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
      virtualizer.scrollToIndex(messages.length - 1, { align: 'end', behavior: 'smooth' })
    }
  }, [messages, virtualizer])

  useEffect(() => {
    const initAgent = async () => {
      const settingsResp = await getSettings()
      const host = settingsResp.success ? settingsResp.settings?.model_server?.host : undefined
      const port = settingsResp.success ? settingsResp.settings?.model_server?.port : undefined
      const url = host && port ? `http://${host}:${port}` : DEFAULT_SIDECAR_URL

      const sid = crypto.randomUUID()
      sessionIdRef.current = sid

      try {
        await agentInit(url)
        await agentCreateSession(sid, projectRoot)

        const history = await agentGetHistory(sid)
        if (history.length > 0) {
          setMessages(history.map(m => ({
            role: m.role as 'user' | 'assistant',
            content: m.content,
          })))
        }
      } catch (e) {
        showToast(t('discover.chat.agentInitFailed', { error: e instanceof Error ? e.message : String(e) }), 'error')
        console.error('Agent init failed:', e)
      }
    }

    void initAgent()

    return () => {
      if (sessionIdRef.current) {
        agentDestroySession(sessionIdRef.current).catch((e) => console.warn('agentDestroySession failed:', e))
      }
    }
  }, [projectRoot, t])

  useEffect(() => {
    if (!projectRoot) return
    listDocumentsTauri(projectRoot).then(resp => {
      if (resp.success) setDocCount(resp.documents.length)
    }).catch((e) => console.warn('listDocumentsTauri failed:', e))
    moleculeStatsTauri(projectRoot).then(resp => {
      if (resp.success) setMolCount(resp.stats.total || 0)
    }).catch((e) => console.warn('moleculeStatsTauri failed:', e))
  }, [projectRoot])

  const sendMessage = useCallback(async () => {
    if (!input.trim() || isLoading || !projectRoot) return

    const userMsg = input.trim()
    isSubmittingRef.current = true
    setInput('')
    onQueryChange(userMsg)

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
                ? { ...m, content: t('discover.chat.error', { error }) }
                : m
              )
            )
          }
        },
      )
    } catch (e) {
      setMessages(prev =>
        prev.map(m => m.id === assistantMsgId
          ? { ...m, content: t('discover.chat.networkError', { error: e instanceof Error ? e.message : String(e) }) }
          : m
        )
      )
    } finally {
      setIsLoading(false)
    }
  }, [input, isLoading, messages, onQueryChange, projectRoot, t])

  return (
    <div className="discover-chat-panel">
      <div className="discover-chat-context">
        <ChatContextChip icon={<FolderIcon size={14} />} label={projectRoot ? projectRoot.split('/').pop() || projectRoot : t('discover.chat.noProject')} />
        <ChatContextChip icon={<FileTextIcon size={14} />} label={t('discover.chat.documentsCount', { count: docCount })} />
        <ChatContextChip icon={<FlaskIcon size={14} />} label={t('discover.chat.moleculesCount', { count: molCount })} />
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
