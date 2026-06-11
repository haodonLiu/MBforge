/**
 * 科学/化学类图标：分子、烧瓶等
 */
import type { FC } from 'react'
import { baseSvg, type IconProps } from './types'

export const FlaskIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <path d="M10 2v7.31" />
      <path d="M14 9.3V1.99" />
      <path d="M8.5 2h7" />
      <path d="M14 9.3a6.5 6.5 0 1 1-4 0" />
      <path d="M5.58 16.5h12.85" />
    </>,
    size,
  )

export const SparklesIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
      <path d="M19 14l.7 2.1L22 17l-2.3.9L19 20l-.7-2.1L16 17l2.3-.9L19 14z" />
    </>,
    size,
  )

export const TargetIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </>,
    size,
  )

export const BarChartIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <line x1="12" y1="20" x2="12" y2="10" />
      <line x1="18" y1="20" x2="18" y2="4" />
      <line x1="6" y1="20" x2="6" y2="16" />
    </>,
    size,
  )

export const ClusterIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <circle cx="8" cy="8" r="3" />
      <circle cx="16" cy="8" r="3" />
      <circle cx="8" cy="16" r="3" />
      <circle cx="16" cy="16" r="3" />
      <line x1="10.5" y1="8" x2="13.5" y2="8" />
      <line x1="8" y1="10.5" x2="8" y2="13.5" />
      <line x1="16" y1="10.5" x2="16" y2="13.5" />
      <line x1="10.5" y1="16" x2="13.5" y2="16" />
    </>,
    size,
  )

export const NetworkIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <circle cx="5" cy="6" r="3" />
      <circle cx="19" cy="6" r="3" />
      <circle cx="12" cy="18" r="3" />
      <line x1="7.5" y1="7.5" x2="10.5" y2="16" />
      <line x1="16.5" y1="7.5" x2="13.5" y2="16" />
    </>,
    size,
  )

export const FilterIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <polygon points="3 5 12 14 12 20 15 20 15 14 21 5" />
    </>,
    size,
  )
