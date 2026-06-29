import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../_utils', () => ({
  httpPost: vi.fn(),
  httpGet: vi.fn(),
  httpPut: vi.fn(),
  httpDelete: vi.fn(),
  invokeWithError: vi.fn((_fn: () => Promise<unknown>) => _fn()),
}))

import { httpPost } from '../_utils'
import { auditLogGet, type AuditEntry } from '../audit'

const mockHttpPost = vi.mocked(httpPost)

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
    mockHttpPost.mockResolvedValue(stub as never)

    const result = await auditLogGet('/tmp/proj', 'trace-1', 50)

    expect(result).toHaveLength(2)
    expect(result[0].action).toBe('llm_call')
    expect(result[0].tokens_used).toBe(150)
    expect(result[1].details['tool']).toBe('search')
    expect(httpPost).toHaveBeenCalledWith('/api/v1/audit/log-get', {
      projectRoot: '/tmp/proj',
      traceId: 'trace-1',
      limit: 50,
    })
  })

  it('uses default limit 200 when omitted', async () => {
    mockHttpPost.mockResolvedValue([] as never)

    await auditLogGet('/tmp/proj')

    expect(httpPost).toHaveBeenCalledWith('/api/v1/audit/log-get', {
      projectRoot: '/tmp/proj',
      traceId: null,
      limit: 200,
    })
  })

  it('passes null traceId when not filtering', async () => {
    mockHttpPost.mockResolvedValue([] as never)

    await auditLogGet('/tmp/proj')

    const callArgs = mockHttpPost.mock.calls[0]?.[1] as Record<string, unknown>
    expect(callArgs.traceId).toBeNull()
  })

  it('handles empty audit log gracefully', async () => {
    mockHttpPost.mockResolvedValue([] as never)

    const result = await auditLogGet('/tmp/empty')
    expect(result).toEqual([])
    expect(Array.isArray(result)).toBe(true)
  })
})
