import type { ChangeEvent } from 'react'

export interface SelectOption {
  value: string
  label: string
}

export interface SelectProps {
  value: string
  onChange: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  disabled?: boolean
  style?: React.CSSProperties
  className?: string
}

/**
 * Select 下拉选择组件。
 *
 * 统一封装原生 select 的样式，替换散落在各处的重复内联样式。
 */
export default function Select({
  value,
  onChange,
  options,
  placeholder = '请选择…',
  disabled = false,
  style,
  className,
}: SelectProps) {
  const handleChange = (e: ChangeEvent<HTMLSelectElement>) => {
    onChange(e.target.value)
  }

  return (
    <select
      value={value}
      onChange={handleChange}
      disabled={disabled}
      className={className}
      style={{
        width: '100%',
        padding: '8px 32px 8px 10px',
        borderRadius: 6,
        border: '1px solid var(--border)',
        background: 'var(--bg-base)',
        color: 'var(--text-primary)',
        fontSize: 13,
        appearance: 'none',
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23999' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
        backgroundRepeat: 'no-repeat',
        backgroundPosition: 'right 10px center',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
        outline: 'none',
        transition: 'border-color 0.2s, box-shadow 0.2s',
        ...style,
      }}
    >
      <option value="">{placeholder}</option>
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}
