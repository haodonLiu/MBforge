/** useDocResult — listen to `EVT_DOC_RESULT` and return the latest `DocumentReport`.
 *
 * Usage:
 * ```ts
 * const { report, litReviewed, litDecision } = useDocResult()
 * // report = 最新文档报告（含化合物 / 活性 / 关键发现）
 * // litReviewed = LitAgent 是否在 Stage 4 后做过二次审阅
 * // litDecision = LitAgent 决策摘要（仅当 litReviewed=true 时有意义）
 * ```
 */
import { useEffect, useState } from 'react'
import { listen } from '@tauri-apps/api/event'
import { EVT } from '../api/tauri-events'
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

  useEffect(() => {
    const unlisten = listen<DocumentReport>(EVT.DocResult, (event) => {
      const report = event.payload
      setState({
        report,
        litReviewed: report?.lit_reviewed ?? false,
        litDecision: report?.lit_decision_summary ?? null,
        lastEventAt: Date.now(),
      })
    })
    return () => {
      unlisten.then((u) => u())
    }
  }, [])

  return state
}
