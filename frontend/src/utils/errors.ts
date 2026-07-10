/**
 * MBForge 结构化错误处理系统。
 *
 * - `AppError`：带 errorCode + severity + category + context 的可序列化错误类
 * - `errorCodes`：统一错误码枚举
 * - `Severity`：分级严重度（debug/info/warning/error/fatal），对接后端 logger 等级
 * - `getErrorMessage`：错误码 → 用户友好文案
 */

export enum ErrorCode {
  Unknown = 'UNKNOWN',
  Network = 'NETWORK',
  ApiError = 'API_ERROR',
  SettingsLoad = 'SETTINGS_LOAD',
  SettingsSave = 'SETTINGS_SAVE',
  ProjectOpen = 'PROJECT_OPEN',
  PdfParse = 'PDF_PARSE',
  MoleculeSearch = 'MOLECULE_SEARCH',
  ModelNotAvailable = 'MODEL_NOT_AVAILABLE',
}

export enum Severity {
  Debug = 'DEBUG',
  Info = 'INFO',
  Warning = 'WARNING',
  Error = 'ERROR',
  Fatal = 'FATAL',
}

/** `Severity` ↔ backend logger level mapping (mirrors Python `http_status_to_severity`). */
const SEVERITY_FROM_HTTP: Record<number, Severity> = {
  400: Severity.Warning,
  401: Severity.Warning,
  403: Severity.Warning,
  404: Severity.Info,
  409: Severity.Warning,
  422: Severity.Warning,
  500: Severity.Error,
  502: Severity.Error,
  503: Severity.Error,
  504: Severity.Error,
}

export function severityFromHttpStatus(status: number): Severity {
  return SEVERITY_FROM_HTTP[status] ?? Severity.Error
}

export interface AppErrorOpts {
  severity?: Severity
  category?: string
  context?: Record<string, unknown>
  /** Wall-clock seconds (matches backend `time.time()`); absent for purely-local errors. */
  timestamp?: number
}

export class AppError extends Error {
  public readonly errorCode: ErrorCode
  public readonly severity?: Severity
  public readonly category?: string
  public readonly context?: Record<string, unknown>
  public readonly timestamp?: number

  constructor(errorCode: ErrorCode, message: string, opts?: AppErrorOpts | Record<string, unknown>) {
    super(message)
    this.name = 'AppError'
    this.errorCode = errorCode
    if (opts) {
      // Accept legacy positional context (`new AppError(c, m, { foo: 1 }`) by
      // recognizing the `severity`-less shape: if `severity` is missing AND
      // `context` is missing, treat the whole bag as context. Otherwise, treat
      // as the new opts form. This keeps existing `new AppError(c, m, ctx)`
      // call sites working while letting the new fields pass through.
      if ('severity' in opts || 'category' in opts || 'timestamp' in opts) {
        this.severity = opts.severity as Severity | undefined
        this.category = opts.category as string | undefined
        this.context = opts.context as Record<string, unknown> | undefined
        this.timestamp = opts.timestamp as number | undefined
      } else {
        this.context = opts as Record<string, unknown>
      }
    }
  }

  toJSON() {
    return {
      name: this.name,
      errorCode: this.errorCode,
      message: this.message,
      severity: this.severity,
      category: this.category,
      context: this.context,
      timestamp: this.timestamp,
    }
  }
}

const ERROR_MESSAGES: Record<ErrorCode, string> = {
  [ErrorCode.Unknown]: '发生了未知错误，请重试',
  [ErrorCode.Network]: '网络连接异常，请检查网络后重试',
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

export function toAppError(
  err: unknown,
  fallbackCode: ErrorCode = ErrorCode.Unknown,
  opts?: AppErrorOpts,
): AppError {
  if (err instanceof AppError) {
    // Promote passed-in severity/category when caller wants to override.
    if (!opts) return err
    return new AppError(err.errorCode, err.message, { ...err.toJSON(), ...opts })
  }
  const message = err instanceof Error ? err.message : String(err)
  return new AppError(fallbackCode, message, opts)
}
