import { motion } from 'framer-motion'
import Card from '../ui/Card'
import Badge from '../ui/Badge'
import { fadeUp } from '../../hooks/useAnimations'

export interface DashboardStatCardProps {
  label: string
  value: number | string
  delta?: number
  subValue?: string
  icon: React.ReactNode
  color: string
  trend?: number[]
  delay?: number
}

/**
 * 仪表盘统计卡片组件。
 */
export default function DashboardStatCard({
  label,
  value,
  delta,
  subValue,
  icon,
  color,
  delay = 0,
}: DashboardStatCardProps) {
  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      animate="visible"
      transition={{ delay }}
    >
      <Card hoverable style={{ padding: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: color + '20', color,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {icon}
          </div>
          {delta !== undefined && (
            <Badge variant={delta >= 0 ? 'success' : 'danger'}>
              {delta >= 0 ? '+' : ''}{delta}%
            </Badge>
          )}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
          {label}
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginTop: 4 }}>
          {typeof value === 'number' ? value.toLocaleString() : value}
        </div>
        {subValue && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{subValue}</div>
        )}
      </Card>
    </motion.div>
  )
}
