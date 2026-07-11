import type { ReactNode } from 'react'

export interface EmptyStateProps {
  message: string
  icon?: ReactNode
  error?: boolean
  action?: { label: string; onClick: () => void }
  style?: React.CSSProperties
  className?: string
}

export default function EmptyState({ message, icon, error = false, action, style, className }: EmptyStateProps) {
  return (
    <div
      className={className}
      style={{
        padding: '40px',
        textAlign: 'center',
        color: error ? 'var(--danger)' : 'var(--text-muted)',
        background: 'var(--bg-surface)',
        borderRadius: '12px',
        border: error ? '1px solid var(--border)' : undefined,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '12px',
        ...style,
      }}
    >
      {icon}
      <span style={{ fontSize: '13px' }}>{message}</span>
      {action && (
        <button
          type="button"
          className="btn btn-primary"
          style={{ marginTop: '8px' }}
          onClick={action.onClick}
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
