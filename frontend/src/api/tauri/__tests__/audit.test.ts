import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

import { invoke } from '@tauri-apps/api/core'
import { auditLogGet, type AuditEntry } from '../audit'

const mockInvoke = vi.mocked(invoke)

// 类型 hack: vi.mocked(invoke) 的 mock.calls 类型推断为 unknown[][]，
// 但实际 invoke(cmd, args) 是 (string, Record<string, unknown>)。
// 我们只断言 cmd 名 + 关键 args 字段，强制 cast 即可。
type InvokeCall = [string, Record<string, unknown>]

function lastCallArgs(): Record<string, unknown> {
  const calls = mockInvoke.mock.calls as unknown as InvokeCall[]
  return calls[calls.length - 1]?.[1] ?? {}
}

describe('auditLogGet', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('forwards projectRoot and returns parsed entries', async () => {
    const stub: AuditEntry[] = [
      {
        trace_id: 'trace-1',
        span_id: 'agent-chat',
        timestamp: 1700000000.5,
        action: 'llm_call',
        details: { model: 'qwen' },
        tokens_used: 150,
        duration_ms: 200,
      },
      {
        trace_id: 'trace-1',
        span_id: 'agent-chat.0',
        timestamp: 1700000001.0,
        action: 'tool_call',
        details: { tool: 'search', args: { q: 'aspirin' } },
        tokens_used: 0,
        duration_ms: 50,
      },
    ]
    mockInvoke.mockResolvedValue(stub)

    const result = await auditLogGet('/tmp/proj', 'trace-1', 50)

    expect(result).toHaveLength(2)
    expect(result[0].action).toBe('llm_call')
    expect(result[0].tokens_used).toBe(150)
    expect(result[1].details['tool']).toBe('search')
    expect(mockInvoke).toHaveBeenCalledWith('audit_log_get', {
      projectRoot: '/tmp/proj',
      traceId: 'trace-1',
      limit: 50,
    })
  })

  it('uses default limit 200 when omitted', async () => {
    mockInvoke.mockResolvedValue([])

    await auditLogGet('/tmp/proj')

    expect(mockInvoke).toHaveBeenCalledWith('audit_log_get', {
      projectRoot: '/tmp/proj',
      traceId: null,
      limit: 200,
    })
  })

  it('passes null traceId when not filtering', async () => {
    mockInvoke.mockResolvedValue([])

    await auditLogGet('/tmp/proj')

    const args = lastCallArgs()
    expect(args.traceId).toBeNull()
  })

  it('handles empty audit log gracefully', async () => {
    mockInvoke.mockResolvedValue([])

    const result = await auditLogGet('/tmp/empty')
    expect(result).toEqual([])
    expect(Array.isArray(result)).toBe(true)
  })
})
