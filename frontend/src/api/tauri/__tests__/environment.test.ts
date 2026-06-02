import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

import { invoke } from '@tauri-apps/api/core'
import { resourcesCheck, resourcesStatus, resourcesGetModelPath, resourcesCatalog } from '../environment'

const mockInvoke = vi.mocked(invoke)

describe('environment API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('resourcesCheck', () => {
    it('returns environment report', async () => {
      const report = {
        python_version: '3.14.2',
        gpu_available: true,
        gpu_name: 'RTX 5070',
        cuda_version: '12.8',
        summary: '9/11 resources ready',
        resources: [
          { id: 'torch', name: 'PyTorch', type: 'python_package', status: 'ready', local_path: '', size_mb: 0, version: '2.11.0', error: '' },
        ],
      }
      mockInvoke.mockResolvedValue(report)

      const result = await resourcesCheck()

      expect(invoke).toHaveBeenCalledWith('resources_check')
      expect(result.summary).toBe('9/11 resources ready')
      expect(result.resources).toHaveLength(1)
    })
  })

  describe('resourcesStatus', () => {
    it('returns single resource status', async () => {
      const status = { id: 'torch', name: 'PyTorch', type: 'python_package', status: 'ready', local_path: '', size_mb: 0, version: '2.11.0', error: '' }
      mockInvoke.mockResolvedValue(status)

      const result = await resourcesStatus('torch')

      expect(invoke).toHaveBeenCalledWith('resources_status', { resourceId: 'torch' })
      expect(result.status).toBe('ready')
    })
  })

  describe('resourcesGetModelPath', () => {
    it('returns model path when available', async () => {
      mockInvoke.mockResolvedValue('/models/embedding')

      const result = await resourcesGetModelPath('embedding')

      expect(invoke).toHaveBeenCalledWith('resources_get_model_path', { resourceId: 'embedding' })
      expect(result).toBe('/models/embedding')
    })

    it('returns null when not available', async () => {
      mockInvoke.mockResolvedValue(null)

      const result = await resourcesGetModelPath('nonexistent')

      expect(result).toBeNull()
    })
  })

  describe('resourcesCatalog', () => {
    it('returns resource catalog', async () => {
      const catalog = [
        { id: 'embedding', name: 'Qwen3-Embedding', type: 'model', description: 'test', size_mb: 1152, license: 'Apache-2.0', ms_repo: 'Qwen/Qwen3-Embedding-0.6B', pip_name: '' },
      ]
      mockInvoke.mockResolvedValue(catalog)

      const result = await resourcesCatalog()

      expect(invoke).toHaveBeenCalledWith('resources_catalog')
      expect(result).toHaveLength(1)
    })
  })
})
