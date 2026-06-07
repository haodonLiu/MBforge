import { useState, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { fadeIn } from '../../hooks/useAnimations'

interface TooltipProps {
  /** 旧 API：纯文本。保留向下兼容。 */
  text?: string
  /** 新 API：可放任意 JSX（如两行布局）。优先于 text。 */
  content?: ReactNode
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
  content,
  children,
  position = 'right',
  trigger = 'hover',
}: TooltipProps) {
  const [show, setShow] = useState(false)
  const isRich = content !== undefined

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
              padding: isRich ? '8px 12px' : '4px 10px',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 500,
              whiteSpace: isRich ? 'normal' : 'nowrap',
              pointerEvents: 'none',
              zIndex: 100,
              minWidth: isRich ? 'max-content' : undefined,
              boxShadow: isRich ? '0 4px 12px rgba(0,0,0,0.2)' : undefined,
            }}
          >
            {content ?? text}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
