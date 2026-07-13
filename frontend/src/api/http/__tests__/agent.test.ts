import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../_utils', () => ({
  httpPost: vi.fn(),
  httpGet: vi.fn(),
  httpPut: vi.fn(),
  httpDelete: vi.fn(),
  invokeWithError: vi.fn((_fn: () => Promise<unknown>) => _fn()),
  API_BASE: '/api/v1',
}))

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
}
Object.defineProperty(globalThis, 'EventSource', { value: MockEventSource, writable: true })

import { httpPost, httpGet, httpPut, httpDelete } from '../_utils'
import {
  agentInit,
  agentCreateSession,
  agentChat,
  agentChatStream,
  agentSwitchProject,
  agentClear,
  agentDestroySession,
  agentGetHistory,
  getLlmEnvConfig,
  testLlmConnection,
} from '../agent'

const mockHttpPost = vi.mocked(httpPost)
const mockHttpGet = vi.mocked(httpGet)
const mockHttpPut = vi.mocked(httpPut)
const mockHttpDelete = vi.mocked(httpDelete)

describe('agent API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    MockEventSource.instances = []
  })

  describe('agentInit', () => {
    it('calls httpPost with sidecar_url', async () => {
      mockHttpPost.mockResolvedValue(undefined)

      await agentInit('http://localhost:18792')

      expect(httpPost).toHaveBeenCalledWith('/api/v1/agent/init', {
        sidecar_url: 'http://localhost:18792',
      })
    })
  })

  describe('getLlmEnvConfig / testLlmConnection', () => {
    it('getLlmEnvConfig calls httpGet /api/v1/settings', async () => {
      const settingsResp = {
        success: true,
        settings: {
          llm: {
            provider: 'openai_compatible',
            base_url: 'https://api.openai.com/v1',
            api_key: 'sk-xxx',
            model_name: 'gpt-4o',
          },
        },
      }
      mockHttpGet.mockResolvedValue(settingsResp)

      const result = await getLlmEnvConfig()

      expect(httpGet).toHaveBeenCalledWith('/api/v1/settings')
      expect(result.provider).toBe('openai_compatible')
      expect(result.base_url).toBe('https://api.openai.com/v1')
      expect(result.api_key_set).toBe(true)
      expect(result.model).toBe('gpt-4o')
    })

    it('testLlmConnection calls httpGet /api/v1/settings and measures latency', async () => {
      const settingsResp = {
        success: true,
        settings: {
          llm: {
            provider: 'openai_compatible',
            base_url: 'https://api.openai.com/v1',
            api_key: 'sk-xxx',
            model_name: 'gpt-4o',
          },
        },
      }
      mockHttpGet.mockResolvedValue(settingsResp)

      const result = await testLlmConnection()

      expect(httpGet).toHaveBeenCalledWith('/api/v1/settings')
      expect(result.status).toBe('ok')
      expect(result.latency_ms).toBeGreaterThanOrEqual(0)
    })
  })

  describe('agentCreateSession', () => {
    it('creates session with project root', async () => {
      mockHttpPost.mockResolvedValue(undefined)

      await agentCreateSession('session-1', '/project')

      expect(httpPost).toHaveBeenCalledWith('/api/v1/agent/session', {
        session_id: 'session-1',
        library_root: '/project',
      })
    })

    it('creates session without project root', async () => {
      mockHttpPost.mockResolvedValue(undefined)

      await agentCreateSession('session-1')

      expect(httpPost).toHaveBeenCalledWith('/api/v1/agent/session', {
        session_id: 'session-1',
        library_root: null,
      })
    })
  })

  describe('agentChat', () => {
    it('returns chat reply', async () => {
      mockHttpPost.mockResolvedValue({ success: true, reply: 'Hello!' })

      const result = await agentChat('session-1', 'Hi')

      expect(httpPost).toHaveBeenCalledWith('/api/v1/agent/session/session-1/chat', {
        user_input: 'Hi',
      })
      expect(result).toBe('Hello!')
    })
  })

  describe('agentChatStream', () => {
    it('returns a cleanup function', async () => {
      const cleanup = await agentChatStream('session-1', 'Hi', vi.fn(), vi.fn(), vi.fn())
      expect(typeof cleanup).toBe('function')
    })

    it('opens a relative EventSource URL instead of a hardcoded host', async () => {
      await agentChatStream('session-1', 'Hi there', vi.fn(), vi.fn(), vi.fn())
      expect(MockEventSource.instances).toHaveLength(1)
      expect(MockEventSource.instances[0].url).toBe(
        '/api/v1/agent/session/session-1/chat/stream?user_input=Hi+there',
      )
    })
  })

  describe('agentSwitchProject', () => {
    it('calls httpPut with project info', async () => {
      mockHttpPut.mockResolvedValue(undefined)

      await agentSwitchProject('session-1', '/project', 'MyProject')

      expect(httpPut).toHaveBeenCalledWith('/api/v1/agent/session/session-1/project', {
        library_root: '/project',
      })
    })
  })

  describe('agentClear', () => {
    it('clears session', async () => {
      mockHttpPost.mockResolvedValue(undefined)

      await agentClear('session-1')

      expect(httpPost).toHaveBeenCalledWith('/api/v1/agent/session/session-1/clear')
    })
  })

  describe('agentDestroySession', () => {
    it('destroys session', async () => {
      mockHttpDelete.mockResolvedValue(undefined)

      await agentDestroySession('session-1')

      expect(httpDelete).toHaveBeenCalledWith('/api/v1/agent/session/session-1')
    })
  })

  describe('agentGetHistory', () => {
    it('returns chat history', async () => {
      const messages = [
        { role: 'user', content: 'Hi' },
        { role: 'assistant', content: 'Hello!' },
      ]
      mockHttpGet.mockResolvedValue({ success: true, messages })

      const result = await agentGetHistory('session-1')

      expect(httpGet).toHaveBeenCalledWith('/api/v1/agent/session/session-1/history')
      expect(result).toEqual(messages)
    })
  })
})
