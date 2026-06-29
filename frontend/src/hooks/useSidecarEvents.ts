/** Poll sidecar health status (replaces Tauri IPC listen). */

import { useEffect } from 'react'
import { httpGet } from '../api/tauri/_utils'

export interface SidecarStatusEvent {
  healthy: boolean
  restartCount: number
  state: 'online' | 'offline'
  uptimeSecs: number
  lastError: string | null
}

export function useSidecarEvents() {
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setInterval> | null = null

    const poll = async () => {
      if (cancelled) return
      try {
        const data = await httpGet<{
          healthy: boolean
          restart_count: number
          state: string
          uptime_secs: number
          last_error: string | null
        }>('/api/v1/sidecar/status')
        if (cancelled) return
        console.log(
          `[sidecar status] state=${data.state} healthy=${data.healthy} uptime=${data.uptime_secs}s`,
          data.last_error ? `error=${data.last_error}` : '',
        )
      } catch {
        if (!cancelled) console.warn('[sidecar status] poll failed')
      }
    }

    void poll()
    timer = setInterval(poll, 5000)

    return () => {
      cancelled = true
      if (timer !== null) clearInterval(timer)
    }
  }, [])
}
