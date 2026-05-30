import React from 'react'
import Card from '../ui/Card'
import IconContainer from '../ui/IconContainer'
import Caption from '../ui/Caption'

interface StatCardProps {
  icon: React.ReactNode
  value: string
  label: string
}

export default function StatCard({ icon, value, label }: StatCardProps) {
  return (
    <Card style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <IconContainer>{icon}</IconContainer>
      <div>
        <div style={{ fontSize: '20px', fontWeight: 700 }}>{value}</div>
        <Caption>{label}</Caption>
      </div>
    </Card>
  )
}
