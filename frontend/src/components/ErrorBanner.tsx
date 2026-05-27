interface ErrorBannerProps {
  message: string
  onDismiss?: () => void
}

export default function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  if (!message) return null

  return (
    <div style={{
      padding: '10px 16px',
      background: 'rgba(239, 68, 68, 0.1)',
      border: '1px solid rgba(239, 68, 68, 0.3)',
      borderRadius: '6px',
      color: '#ef4444',
      fontSize: '13px',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '12px',
    }}>
      <span>{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          style={{
            background: 'none',
            border: 'none',
            color: '#ef4444',
            cursor: 'pointer',
            fontSize: '16px',
            padding: '0 4px',
          }}
        >
          x
        </button>
      )}
    </div>
  )
}
