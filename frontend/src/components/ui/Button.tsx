import { motion } from 'framer-motion'
import type { ReactNode, MouseEvent } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'dashed' | 'success'
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
  success:   { background: 'var(--success)', color: '#fff', border: 'none' },
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
    transition: 'background-color 150ms ease, border-color 150ms ease, color 150ms ease, box-shadow 150ms ease, transform 150ms ease',
    lineHeight: 1,
    ...variantStyles[variant],
    ...sizeStyles[size],
    ...style,
  }
  const hoverEffect = isDisabled
    ? undefined
    : variant === 'primary'
      ? { scale: 1.02, boxShadow: '0 8px 20px rgba(79, 70, 229, 0.28)' }
      : variant === 'success'
        ? { scale: 1.02, boxShadow: '0 8px 20px rgba(22, 163, 74, 0.24)' }
      : variant === 'secondary'
        ? { backgroundColor: 'var(--bg-hover)' }
        : { backgroundColor: 'var(--bg-hover)' }

  return (
    <motion.button
      type={type}
      title={title}
      className={className}
      onClick={isDisabled ? undefined : onClick}
      disabled={isDisabled}
      style={base}
      whileHover={hoverEffect}
      whileTap={isDisabled ? undefined : { scale: 0.96 }}
      transition={{ type: 'spring', duration: 0.3, bounce: 0 }}
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
