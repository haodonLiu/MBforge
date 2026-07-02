import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../_utils', () => ({
  httpPost: vi.fn(),
  httpGet: vi.fn(),
  httpPut: vi.fn(),
  httpDelete: vi.fn(),
  invokeWithError: vi.fn((_fn: () => Promise<unknown>) => _fn()),
}))

vi.mock('../sse', () => ({
  connectSSE: vi.fn((_url: string, _onEvent: (event: { data: unknown }) => void) =>
    Promise.resolve(() => {}),
  ),
}))

import { httpPost } from '../_utils'
import { connectSSE } from '../sse'
import { kbSearch, kbSearchStream, kbGetStructure, kbGetPages } from '../kb'

const mockHttpPost = vi.mocked(httpPost)
const mockConnectSSE = vi.mocked(connectSSE)

describe('kb API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('kbSearch', () => {
    it('calls httpPost with correct params', async () => {
      const results = [{ id: '1', text: 'test', metadata: {}, score: 0.9 }]
      mockHttpPost.mockResolvedValue({ success: true, results } as never)

      const result = await kbSearch('/project', 'query', 5)

      expect(httpPost).toHaveBeenCalledWith('/api/v1/kb/search', {
        project_root: '/project',
        query: 'query',
        top_k: 5,
      })
      expect(result).toEqual(results)
    })

    it('uses default topK=5', async () => {
      mockHttpPost.mockResolvedValue({ success: true, results: [] } as never)

      await kbSearch('/project', 'query')

      expect(httpPost).toHaveBeenCalledWith('/api/v1/kb/search', {
        project_root: '/project',
        query: 'query',
        top_k: 5,
      })
    })
  })

  describe('kbSearchStream', () => {
    it('connects to SSE stream', async () => {
      await kbSearchStream('/project', 'query', 10, vi.fn())

      expect(connectSSE).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/kb/search/stream?'),
        expect.any(Function),
      )
    })

    it('calls onChunk when event received', async () => {
      let streamHandler: (event: { data: unknown }) => void = () => {}
      mockConnectSSE.mockImplementation(async (_url: string, handler: any) => {
        streamHandler = handler
        return () => {}
      })

      const onChunk = vi.fn()
      await kbSearchStream('/project', 'query', 10, onChunk)

      streamHandler({
        data: {
          type: 'results',
          results: [{ id: '1', text: 'test', metadata: {}, score: 0.9 }],
          count: 1,
        },
      })

      expect(onChunk).toHaveBeenCalledWith({
        type: 'incremental',
        results: [{ id: '1', text: 'test', metadata: {}, score: 0.9 }],
        count: 1,
        error: null,
      })
    })
  })

  describe('kbGetStructure', () => {
    it('calls httpPost with correct params', async () => {
      const tree = [{ title: 'Intro', node_id: '1', line_num: 0, nodes: [] }]
      mockHttpPost.mockResolvedValue({ success: true, structure: tree } as never)

      const result = await kbGetStructure('/project', 'doc1')

      expect(httpPost).toHaveBeenCalledWith('/api/v1/kb/structure', {
        project_root: '/project',
        doc_id: 'doc1',
      })
      expect(result).toEqual(tree)
    })

    it('returns null when no structure', async () => {
      mockHttpPost.mockResolvedValue({ success: true, structure: null } as never)

      const result = await kbGetStructure('/project', 'doc1')

      expect(result).toBeNull()
    })
  })

  describe('kbGetPages', () => {
    it('calls httpPost with correct params', async () => {
      const pages = [{ page: 1, content: 'text' }]
      mockHttpPost.mockResolvedValue({ success: true, pages } as never)

      const result = await kbGetPages('/project', 'doc1', '1-3')

      expect(httpPost).toHaveBeenCalledWith('/api/v1/kb/pages', {
        project_root: '/project',
        doc_id: 'doc1',
        pages: '1-3',
      })
      expect(result).toEqual(pages)
    })
  })
})
