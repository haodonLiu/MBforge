import type { ChangeEvent, KeyboardEvent, FocusEvent } from 'react'

export interface InputProps {
  value?: string
  defaultValue?: string
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void
  onKeyDown?: (e: KeyboardEvent<HTMLInputElement>) => void
  onFocus?: (e: FocusEvent<HTMLInputElement>) => void
  onBlur?: (e: FocusEvent<HTMLInputElement>) => void
  placeholder?: string
  type?: string
  disabled?: boolean
  error?: boolean
  autoFocus?: boolean
  style?: React.CSSProperties
  className?: string
}

export default function Input({
  value,
  defaultValue,
  onChange,
  onKeyDown,
  onFocus,
  onBlur,
  placeholder,
  type = 'text',
  disabled = false,
  error = false,
  autoFocus,
  style,
  className,
}: InputProps) {
  return (
    <input
      type={type}
      value={value}
      defaultValue={defaultValue}
      onChange={onChange}
      onKeyDown={onKeyDown}
      onFocus={onFocus}
      onBlur={onBlur}
      placeholder={placeholder}
      disabled={disabled}
      autoFocus={autoFocus}
      className={`input ${className || ''}`}
      style={{
        width: '100%',
        boxSizing: 'border-box',
        borderColor: error ? 'var(--danger)' : undefined,
        ...style,
      }}
    />
  )
}
