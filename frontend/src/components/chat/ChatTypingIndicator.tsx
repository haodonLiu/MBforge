import { motion } from 'framer-motion'
import { Avatar } from '../ui'
import { BotIcon } from '../icons'

export default function ChatTypingIndicator() {
  return (
    <div className="chat-typing-row">
      <div className="chat-avatar-wrap">
        <Avatar size={32} variant="bot">
          <BotIcon size={16} />
        </Avatar>
      </div>
      <div className="chat-typing-bubble">
        {[0, 1, 2].map(i => (
          <motion.div
            key={i}
            className="chat-typing-dot"
            animate={{ y: [0, -6, 0], opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15, ease: 'easeInOut' }}
          />
        ))}
      </div>
    </div>
  )
}
