export type AlertVariant = 'success' | 'danger' | 'info'

interface Props {
  message: string
  variant?: AlertVariant
  onDismiss?: () => void
  style?: React.CSSProperties
  className?: string
}

const variantMap: Record<AlertVariant, { color: string; bg: string; border: string }> = {
  success: { color: '#16a34a', bg: 'rgba(22,163,74,0.1)', border: 'rgba(22,163,74,0.3)' },
  danger:  { color: '#ef4444', bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.3)' },
  info:    { color: '#3b82f6', bg: 'rgba(59,130,246,0.1)', border: 'rgba(59,130,246,0.3)' },
}

export default function AlertBanner({ message, variant = 'info', onDismiss, style, className }: Props) {
  const v = variantMap[variant]
  return (
    <div
      className={className}
      style={{
        padding: '10px 16px',
        background: v.bg,
        border: `1px solid ${v.border}`,
        borderRadius: '6px',
        color: v.color,
        fontSize: '13px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '12px',
        ...style,
      }}
    >
      <span>{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          style={{
            background: 'none',
            border: 'none',
            color: v.color,
            cursor: 'pointer',
            fontSize: '16px',
            padding: '0 4px',
            lineHeight: 1,
          }}
        >
          ×
        </button>
      )}
    </div>
  )
}
