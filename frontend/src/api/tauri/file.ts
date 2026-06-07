/** File-level Tauri IPC wrappers. */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

/**
 * 在 Tauri 主进程内读取任意文件字节流（不依赖系统 PDF 阅读器、也不走 asset protocol）。
 *
 * 为什么不用 `convertFileSrc`：
 * - dev 模式下 webview 从 `http://localhost:5173` 加载，asset protocol 返回
 *   `http://asset.localhost/...` 是另一个 origin，被 CORS 挡住。
 * - 通过 Tauri IPC 走自家通道，dev / prod 行为一致，没有跨域问题。
 *
 * 用途：
 * - PdfViewer 拿到 PDF bytes 后用 `new Blob([bytes], {type:'application/pdf'})` 渲染
 * - 分子图（PNG/JPG）用同样方式渲染图片
 */
export async function readFileBytes(projectRoot: string, path: string): Promise<Uint8Array> {
  return invokeWithError(
    () => invoke<number[]>('read_file_bytes', { projectRoot, path }),
    ErrorCode.TauriInvoke,
  ).then((arr) => new Uint8Array(arr))
}
