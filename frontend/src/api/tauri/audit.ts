/** Audit log bridge — HTTP backend.
 *
 * Audit entries are appended by:
 * - `Agent::chat` / `Agent::chat_stream` (LLM calls)
 * - `SpecialistAgent::process` (LLM + tool calls)
 * - `PipelineOutput` related commands (file writes)
 *
 * Each entry is a single line in `<project_root>/.mbforge/audit.jsonl`
 * with the discriminator `action: "llm_call" | "tool_call" | "molecule_add" | ...`.
 */

import { httpPost, invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

/** Audit entry — 与 Rust `AuditEntry` 一一对应 */
export interface AuditEntry {
  trace_id: string
  span_id: string | null
  timestamp: number // Unix seconds (f64 on Rust side; JS treats as number)
  action: string // "llm_call" | "tool_call" | "molecule_add" | ...
  details: Record<string, unknown>
  tokens_used: number
  duration_ms: number
}

/** 读取项目最近 N 条审计记录（默认 200）
 *
 * @param projectRoot 项目根目录 — audit.jsonl 在 `<root>/.mbforge/` 下
 * @param traceId 可选 — 若提供，仅返回该 trace_id 的条目
 * @param limit 最多返回条数（默认 200）
 */
export async function auditLogGet(
  projectRoot: string,
  traceId?: string,
  limit = 200,
): Promise<AuditEntry[]> {
  return invokeWithError(
    () =>
      httpPost<AuditEntry[]>('/api/v1/audit/log-get', {
        projectRoot,
        traceId: traceId ?? null,
        limit,
      }),
    ErrorCode.ApiError,
  )
}
