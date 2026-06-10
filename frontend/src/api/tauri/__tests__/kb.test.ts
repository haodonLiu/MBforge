import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(),
}))

import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { kbSearch, kbSearchStream, kbGetStructure, kbGetPages } from '../kb'

const mockInvoke = vi.mocked(invoke)
const mockListen = vi.mocked(listen)

describe('kb API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('kbSearch', () => {
    it('calls invoke with correct params', async () => {
      const results = [{ id: '1', text: 'test', metadata: {}, score: 0.9 }]
      mockInvoke.mockResolvedValue(results)

      const result = await kbSearch('/project', 'query', 5)

      expect(invoke).toHaveBeenCalledWith('kb_search', {
        root: '/project',
        query: 'query',
        topK: 5,
      })
      expect(result).toEqual(results)
    })

    it('uses default topK=5', async () => {
      mockInvoke.mockResolvedValue([])

      await kbSearch('/project', 'query')

      expect(invoke).toHaveBeenCalledWith('kb_search', {
        root: '/project',
        query: 'query',
        topK: 5,
      })
    })
  })

  describe('kbSearchStream', () => {
    it('invokes kb_search_stream and listens for events', async () => {
      mockInvoke.mockResolvedValue(undefined)
      mockListen.mockResolvedValue(() => {})

      const onChunk = vi.fn()
      await kbSearchStream('/project', 'query', 10, onChunk)

      expect(invoke).toHaveBeenCalledWith('kb_search_stream', {
        root: '/project',
        query: 'query',
        topK: 10,
      })
      expect(listen).toHaveBeenCalled()
    })

    it('calls onChunk when event received', async () => {
      mockInvoke.mockResolvedValue(undefined)
      let eventHandler: Function = () => {}
      mockListen.mockImplementation(async (_event: string, handler: any) => {
        eventHandler = handler
        return () => {}
      })

      const onChunk = vi.fn()
      await kbSearchStream('/project', 'query', 10, onChunk)

      // Simulate event
      eventHandler({
        payload: {
          type: 'first',
          results: [{ id: '1', text: 'test', metadata: {}, score: 0.9 }],
          count: 1,
          error: null,
        },
      })

      expect(onChunk).toHaveBeenCalledWith({
        type: 'first',
        results: [{ id: '1', text: 'test', metadata: {}, score: 0.9 }],
        count: 1,
        error: null,
      })
    })
  })

  describe('kbGetStructure', () => {
    it('calls invoke with correct params', async () => {
      const tree = [{ title: 'Intro', node_id: '1', line_num: 0, nodes: [] }]
      mockInvoke.mockResolvedValue(tree)

      const result = await kbGetStructure('/project', 'doc1')

      expect(invoke).toHaveBeenCalledWith('kb_get_structure', {
        root: '/project',
        docId: 'doc1',
      })
      expect(result).toEqual(tree)
    })

    it('returns null when no structure', async () => {
      mockInvoke.mockResolvedValue(null)

      const result = await kbGetStructure('/project', 'doc1')

      expect(result).toBeNull()
    })
  })

  describe('kbGetPages', () => {
    it('calls invoke with correct params', async () => {
      const pages = [{ page: 1, content: 'text' }]
      mockInvoke.mockResolvedValue(pages)

      const result = await kbGetPages('/project', 'doc1', '1-3')

      expect(invoke).toHaveBeenCalledWith('kb_get_pages', {
        root: '/project',
        docId: 'doc1',
        pages: '1-3',
      })
      expect(result).toEqual(pages)
    })
  })
})
