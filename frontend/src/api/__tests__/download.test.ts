import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({
  fetchJson: vi.fn(),
  sseStream: vi.fn(),
}))

import { fetchJson, sseStream } from '../client'
import { listModels, getModelDir, listDownloaded, deleteModel, checkModelStatus, downloadModel } from '../download'

const mockFetchJson = vi.mocked(fetchJson)
const mockSseStream = vi.mocked(sseStream)

describe('download API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('listModels', () => {
    it('fetches model list', async () => {
      const models = {
        success: true,
        models: [{ id: 'embedding', name: 'Qwen3-Embedding', downloaded: true }],
      }
      mockFetchJson.mockResolvedValue(models)

      const result = await listModels()

      expect(fetchJson).toHaveBeenCalledWith('/api/v1/download/models')
      expect(result).toEqual(models)
    })
  })

  describe('getModelDir', () => {
    it('fetches model directory', async () => {
      mockFetchJson.mockResolvedValue({ success: true, model_dir: '/models' })

      const result = await getModelDir()

      expect(fetchJson).toHaveBeenCalledWith('/api/v1/download/model-dir')
      expect(result.model_dir).toBe('/models')
    })
  })

  describe('listDownloaded', () => {
    it('fetches downloaded models', async () => {
      mockFetchJson.mockResolvedValue({ success: true, models: [], model_dir: '/models' })

      await listDownloaded()

      expect(fetchJson).toHaveBeenCalledWith('/api/v1/download/list-downloaded')
    })
  })

  describe('deleteModel', () => {
    it('deletes model by id', async () => {
      mockFetchJson.mockResolvedValue({ success: true, deleted: '/models/embedding' })

      await deleteModel('embedding')

      expect(fetchJson).toHaveBeenCalledWith('/api/v1/download/delete/embedding', {
        method: 'DELETE',
      })
    })
  })

  describe('checkModelStatus', () => {
    it('checks model status', async () => {
      mockFetchJson.mockResolvedValue({ success: true, downloaded: true })

      await checkModelStatus('embedding')

      expect(fetchJson).toHaveBeenCalledWith('/api/v1/download/status/embedding')
    })
  })

  describe('downloadModel', () => {
    it('starts SSE download stream', () => {
      const onEvent = vi.fn()
      mockSseStream.mockReturnValue(() => {})

      const abort = downloadModel('embedding', onEvent)

      expect(sseStream).toHaveBeenCalledWith(
        '/api/v1/download/download/embedding',
        null,
        onEvent,
        expect.any(Function),
      )
      expect(typeof abort).toBe('function')
    })
  })
})
