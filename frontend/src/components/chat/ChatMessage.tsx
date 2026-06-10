import { Avatar } from '../ui'
import { UserIcon, BotIcon } from '../icons'
import ChatMarkdown from './ChatMarkdown'

export interface LocalMessage {
  id?: string
  role: 'user' | 'assistant'
  content: string
}

interface ChatMessageProps {
  msg: LocalMessage
}

export default function ChatMessage({ msg }: ChatMessageProps) {
  const isUser = msg.role === 'user'

  return (
    <div className={`chat-message-row ${isUser ? 'user' : 'assistant'}`}>
      <div className="chat-message-inner">
        {!isUser && (
          <div className="chat-avatar-wrap">
            <Avatar size={32} variant="bot">
              <BotIcon size={16} />
            </Avatar>
          </div>
        )}
        <div className={`chat-bubble ${isUser ? 'user' : 'assistant'}`}>
          {isUser ? (
            <span className="chat-user-text">{msg.content}</span>
          ) : (
            <ChatMarkdown content={msg.content} />
          )}
        </div>
        {isUser && (
          <div className="chat-avatar-wrap">
            <Avatar size={32} variant="user">
              <UserIcon size={16} />
            </Avatar>
          </div>
        )}
      </div>
    </div>
  )
}
