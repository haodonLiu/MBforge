import Badge from '../ui/Badge'
import type { CorrectionItem } from './CorrectionPanel'

interface StatusBadgeProps {
  status: CorrectionItem['status']
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  switch (status) {
    case 'confirmed':
      return <Badge variant="success" dot>已确认</Badge>
    case 'corrected':
      return <Badge variant="info" dot>已修正</Badge>
    case 'rejected':
      return <Badge variant="danger" dot>已拒绝</Badge>
    default:
      return <Badge variant="warning" dot>待处理</Badge>
  }
}
