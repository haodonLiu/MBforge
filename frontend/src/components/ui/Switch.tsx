export interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  size?: 'sm' | 'md'
  style?: React.CSSProperties
  className?: string
}

/**
 * Switch 开关组件。
 *
 * 替代 settings/SettingRow.tsx 中的 ToggleField，提升复用性。
 */
export default function Switch({
  checked,
  onChange,
  disabled = false,
  size = 'md',
  style,
  className,
}: SwitchProps) {
  const dimensions = size === 'sm'
    ? { width: 36, height: 20, dot: 14, translate: 14 }
    : { width: 44, height: 24, dot: 18, translate: 20 }

  return (
    <label
      className={className}
      style={{
        position: 'relative',
        display: 'inline-block',
        width: dimensions.width,
        height: dimensions.height,
        flexShrink: 0,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        ...style,
      }}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        style={{
          opacity: 0,
          width: 0,
          height: 0,
          position: 'absolute',
        }}
      />
      <span
        style={{
          position: 'absolute',
          inset: 0,
          background: checked ? 'var(--accent)' : 'var(--bg-hover)',
          borderRadius: dimensions.height / 2,
          transition: 'background 0.2s',
        }}
      >
        <span
          style={{
            position: 'absolute',
            width: dimensions.dot,
            height: dimensions.dot,
            left: checked ? undefined : 3,
            right: checked ? 3 : undefined,
            top: 3,
            background: 'white',
            borderRadius: '50%',
            transition: 'all 0.2s',
            boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
          }}
        />
      </span>
    </label>
  )
}
