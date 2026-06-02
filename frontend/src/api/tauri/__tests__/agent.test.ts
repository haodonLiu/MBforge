import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(),
}))

import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import {
  agentInit,
  agentCreateSession,
  agentChat,
  agentChatStream,
  agentSwitchProject,
  agentClear,
  agentDestroySession,
  agentGetHistory,
} from '../agent'

const mockInvoke = vi.mocked(invoke)
const mockListen = vi.mocked(listen)

describe('agent API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('agentInit', () => {
    it('calls invoke with config and sidecarUrl', async () => {
      mockInvoke.mockResolvedValue(undefined)

      const config = {
        provider: 'openai_compatible',
        base_url: 'http://localhost:18792',
        api_key: 'test',
        model_name: 'test-model',
        max_tokens: 4096,
        temperature: 0.7,
        top_p: 0.9,
      }

      await agentInit(config, 'http://localhost:18792')

      expect(invoke).toHaveBeenCalledWith('agent_init', {
        config,
        sidecarUrl: 'http://localhost:18792',
      })
    })
  })

  describe('agentCreateSession', () => {
    it('creates session with project root', async () => {
      mockInvoke.mockResolvedValue(undefined)

      await agentCreateSession('session-1', '/project')

      expect(invoke).toHaveBeenCalledWith('agent_create_session', {
        sessionId: 'session-1',
        projectRoot: '/project',
      })
    })

    it('creates session without project root', async () => {
      mockInvoke.mockResolvedValue(undefined)

      await agentCreateSession('session-1')

      expect(invoke).toHaveBeenCalledWith('agent_create_session', {
        sessionId: 'session-1',
        projectRoot: null,
      })
    })
  })

  describe('agentChat', () => {
    it('returns chat response', async () => {
      mockInvoke.mockResolvedValue('Hello!')

      const result = await agentChat('session-1', 'Hi')

      expect(invoke).toHaveBeenCalledWith('agent_chat', {
        sessionId: 'session-1',
        userInput: 'Hi',
      })
      expect(result).toBe('Hello!')
    })
  })

  describe('agentChatStream', () => {
    it('sets up streaming with event listeners', async () => {
      mockInvoke.mockResolvedValue(undefined)
      mockListen.mockResolvedValue(() => {})

      const onChunk = vi.fn()
      const onDone = vi.fn()
      const onError = vi.fn()

      await agentChatStream('session-1', 'Hi', onChunk, onDone, onError)

      expect(invoke).toHaveBeenCalledWith('agent_chat_stream', {
        sessionId: 'session-1',
        userInput: 'Hi',
      })
      expect(listen).toHaveBeenCalledWith('agent-stream-chunk', expect.any(Function))
      expect(listen).toHaveBeenCalledWith('agent-stream-done', expect.any(Function))
    })
  })

  describe('agentSwitchProject', () => {
    it('calls invoke with project info', async () => {
      mockInvoke.mockResolvedValue(undefined)

      await agentSwitchProject('session-1', '/project', 'MyProject')

      expect(invoke).toHaveBeenCalledWith('agent_switch_project', {
        sessionId: 'session-1',
        projectRoot: '/project',
        projectName: 'MyProject',
      })
    })
  })

  describe('agentClear', () => {
    it('clears session', async () => {
      mockInvoke.mockResolvedValue(undefined)

      await agentClear('session-1')

      expect(invoke).toHaveBeenCalledWith('agent_clear', {
        sessionId: 'session-1',
      })
    })
  })

  describe('agentDestroySession', () => {
    it('destroys session', async () => {
      mockInvoke.mockResolvedValue(undefined)

      await agentDestroySession('session-1')

      expect(invoke).toHaveBeenCalledWith('agent_destroy_session', {
        sessionId: 'session-1',
      })
    })
  })

  describe('agentGetHistory', () => {
    it('returns chat history', async () => {
      const history = [
        { role: 'user', content: 'Hi' },
        { role: 'assistant', content: 'Hello!' },
      ]
      mockInvoke.mockResolvedValue(history)

      const result = await agentGetHistory('session-1')

      expect(invoke).toHaveBeenCalledWith('agent_get_history', {
        sessionId: 'session-1',
      })
      expect(result).toEqual(history)
    })
  })
})
