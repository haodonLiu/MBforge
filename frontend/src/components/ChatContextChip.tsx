import { motion } from 'framer-motion'

interface ChatContextChipProps {
  icon: React.ReactNode
  label: string
}

export default function ChatContextChip({ icon, label }: ChatContextChipProps) {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '6px 12px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '20px',
        fontSize: '12px',
        color: 'var(--text-secondary)',
      }}
    >
      <span style={{ color: 'var(--text-muted)' }}>{icon}</span>
      <span>{label}</span>
    </motion.div>
  )
}
