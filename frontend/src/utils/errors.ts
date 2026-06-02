/**
 * MBForge 结构化错误处理系统。
 *
 * - `AppError`：带 errorCode 的可序列化错误类
 * - `errorCodes`：统一错误码枚举
 * - `getErrorMessage`：错误码 → 用户友好文案
 */

export enum ErrorCode {
  Unknown = 'UNKNOWN',
  Network = 'NETWORK',
  TauriInvoke = 'TAURI_INVOKE',
  ApiError = 'API_ERROR',
  SettingsLoad = 'SETTINGS_LOAD',
  SettingsSave = 'SETTINGS_SAVE',
  ProjectOpen = 'PROJECT_OPEN',
  PdfParse = 'PDF_PARSE',
  MoleculeSearch = 'MOLECULE_SEARCH',
  ModelNotAvailable = 'MODEL_NOT_AVAILABLE',
}

export class AppError extends Error {
  public readonly errorCode: ErrorCode
  public readonly context?: Record<string, unknown>

  constructor(errorCode: ErrorCode, message: string, context?: Record<string, unknown>) {
    super(message)
    this.name = 'AppError'
    this.errorCode = errorCode
    this.context = context
  }

  toJSON() {
    return {
      name: this.name,
      errorCode: this.errorCode,
      message: this.message,
      context: this.context,
    }
  }
}

const ERROR_MESSAGES: Record<ErrorCode, string> = {
  [ErrorCode.Unknown]: '发生了未知错误，请重试',
  [ErrorCode.Network]: '网络连接异常，请检查网络后重试',
  [ErrorCode.TauriInvoke]: '桌面端通信异常，请确认 Tauri 环境正常',
  [ErrorCode.ApiError]: '服务端返回错误',
  [ErrorCode.SettingsLoad]: '加载设置失败',
  [ErrorCode.SettingsSave]: '保存设置失败',
  [ErrorCode.ProjectOpen]: '打开项目失败',
  [ErrorCode.PdfParse]: 'PDF 解析失败',
  [ErrorCode.MoleculeSearch]: '分子搜索失败',
  [ErrorCode.ModelNotAvailable]: '模型不可用，请检查模型配置',
}

export function getErrorMessage(code: ErrorCode): string {
  return ERROR_MESSAGES[code] || ERROR_MESSAGES[ErrorCode.Unknown]
}

export function toAppError(err: unknown, fallbackCode: ErrorCode = ErrorCode.Unknown): AppError {
  if (err instanceof AppError) return err
  const message = err instanceof Error ? err.message : String(err)
  return new AppError(fallbackCode, message)
}
