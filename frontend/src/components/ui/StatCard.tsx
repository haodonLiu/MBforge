export interface StatCardProps {
  label: string
  value: string | number
  icon?: React.ReactNode
  style?: React.CSSProperties
}

export default function StatCard({ label, value, icon, style }: StatCardProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '16px',
        background: '#fafafa',
        borderRadius: '10px',
        border: '1px solid #e5e5e5',
        ...style,
      }}
    >
      {icon && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '40px',
            height: '40px',
            borderRadius: '10px',
            background: '#f0f0f0',
            color: '#666',
          }}
        >
          {icon}
        </div>
      )}
      <div>
        <div style={{ fontSize: '11px', color: '#999', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          {label}
        </div>
        <div style={{ fontSize: '20px', fontWeight: 700, color: '#1a1a1a' }}>
          {value}
        </div>
      </div>
    </div>
  )
}
