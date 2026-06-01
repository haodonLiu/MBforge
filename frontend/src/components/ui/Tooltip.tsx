import { useState, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { fadeIn } from '../../hooks/useAnimations'

interface TooltipProps {
  text: string
  children: ReactNode
  /** 显示在子元素的哪一侧 */
  position?: 'right' | 'left' | 'top' | 'bottom'
  /** 触发方式 */
  trigger?: 'hover' | 'click'
}

const positionStyles: Record<NonNullable<TooltipProps['position']>, React.CSSProperties> = {
  right:  { left: 'calc(100% + 8px)', top: '50%', transform: 'translateY(-50%)' },
  left:   { right: 'calc(100% + 8px)', top: '50%', transform: 'translateY(-50%)' },
  top:    { bottom: 'calc(100% + 8px)', left: '50%', transform: 'translateX(-50%)' },
  bottom: { top: 'calc(100% + 8px)', left: '50%', transform: 'translateX(-50%)' },
}

export default function Tooltip({
  text,
  children,
  position = 'right',
  trigger = 'hover',
}: TooltipProps) {
  const [show, setShow] = useState(false)

  const eventHandlers = trigger === 'hover'
    ? { onMouseEnter: () => setShow(true), onMouseLeave: () => setShow(false) }
    : { onClick: () => setShow(!show), onMouseLeave: () => setShow(false) }

  return (
    <div style={{ position: 'relative' }} {...eventHandlers}>
      {children}
      <AnimatePresence>
        {show && (
          <motion.div
            variants={fadeIn}
            initial="hidden"
            animate="visible"
            exit="hidden"
            style={{
              position: 'absolute',
              ...positionStyles[position],
              background: 'var(--accent)',
              color: '#fff',
              padding: '4px 10px',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 500,
              whiteSpace: 'nowrap',
              pointerEvents: 'none',
              zIndex: 100,
            }}
          >
            {text}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
