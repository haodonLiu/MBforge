/**
 * 品牌 / Logo 类图标
 */
import type { FC } from 'react'
import type { IconProps } from './types'

export const MoleculeLogo: FC<IconProps> = ({ size = 72 }) => (
  <svg width={size} height={size} viewBox="0 0 72 72" fill="none">
    <rect width="72" height="72" rx="18" fill="#1a1a2e" />
    {/* 上方苯环 */}
    <polygon
      points="36,15 47.8,21.8 47.8,35.4 36,42.2 24.2,35.4 24.2,21.8"
      stroke="white" strokeWidth="3" strokeLinejoin="round"
    />
    {/* 左下苯环 */}
    <polygon
      points="18.1,36.6 29.9,29.8 41.7,36.6 41.7,50.2 29.9,57 18.1,50.2"
      stroke="white" strokeWidth="3" strokeLinejoin="round"
    />
    {/* 右下苯环 */}
    <polygon
      points="53.9,36.6 65.7,29.8 65.7,43.4 53.9,50.2 42.1,43.4 42.1,29.8"
      stroke="white" strokeWidth="3" strokeLinejoin="round"
    />
    {/* 连接线 */}
    <line x1="36" y1="42" x2="29.9" y2="29.8" stroke="white" strokeWidth="2.5" />
    <line x1="36" y1="42" x2="42.1" y2="29.8" stroke="white" strokeWidth="2.5" />
  </svg>
)
