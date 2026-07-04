/** useDocResult — poll the latest DocumentReport for the current project. */
import { useEffect, useState, useRef } from 'react'
import { httpGet } from '../api/http/_utils'
import type { DocumentReport } from '../types'

export interface UseDocResult {
  report: DocumentReport | null
  litReviewed: boolean
  litDecision: string | null
  lastEventAt: number | null
}

export function useDocResult(): UseDocResult {
  const [state, setState] = useState<UseDocResult>({
    report: null,
    litReviewed: false,
    litDecision: null,
    lastEventAt: null,
  })

  const lastEtagRef = useRef<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setInterval> | null = null

    const poll = async () => {
      if (cancelled) return
      try {
        const report = await httpGet<DocumentReport>('/api/v1/documents/latest-report')
        if (cancelled) return
        const etag = report?.id ?? null
        if (etag === lastEtagRef.current) return
        lastEtagRef.current = etag
        setState({
          report,
          litReviewed: report?.lit_reviewed ?? false,
          litDecision: report?.lit_decision_summary ?? null,
          lastEventAt: Date.now(),
        })
      } catch {
        if (!cancelled) console.warn('[useDocResult] poll failed')
      }
    }

    timer = setInterval(poll, 3000)
    return () => {
      cancelled = true
      if (timer !== null) clearInterval(timer)
    }
  }, [])

  return state
}
