import { motion } from 'framer-motion'
import type { ReactNode, MouseEvent } from 'react'

interface Props {
  children: ReactNode
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void
  disabled?: boolean
  title?: string
  style?: React.CSSProperties
  className?: string
  whileHoverScale?: number
  whileTapScale?: number
}

export default function ScaleButton({
  children,
  onClick,
  disabled,
  title,
  style,
  className,
  whileHoverScale = 1.02,
  whileTapScale = 0.96,
}: Props) {
  return (
    <motion.button
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={className}
      style={{ ...style, cursor: disabled ? 'not-allowed' : 'pointer' }}
      whileHover={disabled ? undefined : { scale: whileHoverScale }}
      whileTap={disabled ? undefined : { scale: whileTapScale }}
      transition={{ duration: 0.15 }}
    >
      {children}
    </motion.button>
  )
}
