import { motion } from 'framer-motion'
import type { ReactNode, MouseEvent } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'dashed'
export type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps {
  children?: ReactNode
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  disabled?: boolean
  icon?: ReactNode
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void
  type?: 'button' | 'submit' | 'reset'
  style?: React.CSSProperties
  className?: string
  title?: string
}

const variantStyles: Record<ButtonVariant, React.CSSProperties> = {
  primary:   { background: 'var(--accent)', color: '#fff', border: 'none' },
  secondary: { background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' },
  ghost:     { background: 'transparent', color: 'var(--text-secondary)', border: 'none' },
  danger:    { background: 'rgba(220, 38, 38, 0.1)', color: '#dc2626', border: '1px solid rgba(220,38,38,0.3)' },
  dashed:    { background: 'none', color: 'var(--text-secondary)', border: '1px dashed var(--border)' },
}

const sizeStyles: Record<ButtonSize, React.CSSProperties> = {
  sm: { padding: '6px 16px', fontSize: '12px' },
  md: { padding: '8px 16px', fontSize: '13px' },
  lg: { padding: '10px 20px', fontSize: '14px' },
}

export default function Button({
  children,
  variant = 'secondary',
  size = 'md',
  loading = false,
  disabled = false,
  icon,
  onClick,
  type = 'button',
  style,
  className,
  title,
}: ButtonProps) {
  const isDisabled = disabled || loading
  const base: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    borderRadius: '10px',
    fontWeight: 500,
    cursor: isDisabled ? 'not-allowed' : 'pointer',
    opacity: isDisabled ? 0.6 : 1,
    transition: 'all 0.15s',
    lineHeight: 1,
    ...variantStyles[variant],
    ...sizeStyles[size],
    ...style,
  }

  return (
    <motion.button
      type={type}
      title={title}
      className={className}
      onClick={isDisabled ? undefined : onClick}
      disabled={isDisabled}
      style={base}
      whileHover={isDisabled ? undefined : { scale: 1.03 }}
      whileTap={isDisabled ? undefined : { scale: 0.97 }}
      transition={{ duration: 0.15 }}
    >
      {loading && (
        <span style={{
          display: 'inline-block',
          width: '14px',
          height: '14px',
          border: '2px solid currentColor',
          borderTopColor: 'transparent',
          borderRadius: '50%',
          animation: 'spin 0.6s linear infinite',
          opacity: 0.7,
        }} />
      )}
      {icon}
      {children}
    </motion.button>
  )
}
