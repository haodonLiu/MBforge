import React from 'react'

interface StatCardProps {
  icon: React.ReactNode
  value: string
  label: string
}

export default function StatCard({ icon, value, label }: StatCardProps) {
  return (
    <div style={{
      padding: '20px',
      background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderRadius: '12px',
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
    }}>
      <div style={{ color: 'var(--text-muted)' }}>{icon}</div>
      <div>
        <div style={{
          fontSize: '20px',
          fontWeight: 700,
        }}>{value}</div>
        <div style={{
          fontSize: '12px',
          color: 'var(--text-muted)',
        }}>{label}</div>
      </div>
    </div>
  )
}
