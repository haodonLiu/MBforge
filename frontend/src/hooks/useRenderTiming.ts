/** Development-only render timing hook.
 *
 * Usage:
 *   useRenderTiming('MyComponent')
 *
 * In production this is a no-op.
 */

import { useEffect, useRef } from 'react'

const isDev = import.meta.env.DEV

export function useRenderTiming(componentName: string) {
  if (!isDev) return

  const startTime = useRef(performance.now())

  useEffect(() => {
    const mountMs = performance.now() - startTime.current
    if (mountMs > 16) {
      console.warn(`[render-timing] ${componentName} mount: ${mountMs.toFixed(2)}ms (>1 frame)`)
    } else {
      console.log(`[render-timing] ${componentName} mount: ${mountMs.toFixed(2)}ms`)
    }
  })

  useEffect(() => {
    return () => {
      console.log(`[render-timing] ${componentName} unmount`)
    }
  }, [componentName])
}
