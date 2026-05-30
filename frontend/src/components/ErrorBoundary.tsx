import { Component, type ReactNode } from 'react'
import { AlertIcon } from './icons'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: undefined })
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            height: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            background: 'var(--bg-base)',
          }}
        >
          <div
            style={{
              maxWidth: '480px',
              width: '100%',
              textAlign: 'center',
              padding: '40px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: '16px',
            }}
          >
            <div
              style={{
                width: '56px',
                height: '56px',
                borderRadius: '14px',
                background: 'rgba(220, 38, 38, 0.1)',
                color: '#dc2626',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 20px',
              }}
            >
              <AlertIcon size={28} />
            </div>
            <h2
              style={{
                fontSize: '18px',
                fontWeight: 600,
                color: 'var(--text-primary)',
                marginBottom: '8px',
              }}
            >
              出现错误
            </h2>
            <p
              style={{
                fontSize: '14px',
                color: 'var(--text-secondary)',
                marginBottom: '20px',
                lineHeight: 1.5,
              }}
            >
              应用遇到了意外问题。您可以尝试刷新页面恢复。
            </p>
            {this.state.error && (
              <pre
                style={{
                  fontSize: '12px',
                  color: 'var(--text-muted)',
                  background: 'var(--bg-base)',
                  padding: '12px',
                  borderRadius: '8px',
                  textAlign: 'left',
                  overflow: 'auto',
                  maxHeight: '120px',
                  marginBottom: '20px',
                  fontFamily: "'Consolas', 'Monaco', monospace",
                }}
              >
                {this.state.error.name}: {this.state.error.message}
              </pre>
            )}
            <button
              onClick={this.handleReset}
              style={{
                padding: '10px 24px',
                background: 'var(--accent)',
                color: '#fff',
                border: 'none',
                borderRadius: '10px',
                fontSize: '14px',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--accent-hover)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'var(--accent)'
              }}
            >
              刷新页面
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
