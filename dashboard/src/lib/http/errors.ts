/**
 * 请求客户端统一的错误类型。
 *
 * 请求层所有失败（HTTP 错误、解析失败、网络异常、认证失效）都以 ApiError 抛出：
 * - message 已经过格式化，可直接用于 toast / 页面渲染；
 * - status 是 HTTP 状态码，请求未到达服务器（网络层失败）时为 undefined；
 * - detail 保留后端返回的原始错误体，便于调试与精细化处理；
 * - errorCode 是 SSD1 后端返回的结构化错误码（如 AUTH_FAILED、PARAM_CONFIG_INVALID）。
 */
export class ApiError extends Error {
  /** HTTP 状态码；网络层失败（请求未到达服务器）时为 undefined */
  readonly status?: number
  /** 后端返回的原始错误体（JSON 解析结果或原始文本） */
  readonly detail?: unknown
  /** SSD1 后端错误码（如 AUTH_FAILED、PARAM_CONFIG_INVALID） */
  readonly errorCode?: string

  constructor(
    message: string,
    options: { status?: number; detail?: unknown; cause?: unknown; errorCode?: string } = {}
  ) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause })
    this.name = 'ApiError'
    this.status = options.status
    this.detail = options.detail
    this.errorCode = options.errorCode
  }
}

/** 判断是否为认证类错误（error_code 以 AUTH_ 开头） */
export function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && error.errorCode?.startsWith('AUTH_') === true
}

/** 判断是否为参数类错误（error_code 以 PARAM_ 开头） */
export function isParamError(error: unknown): boolean {
  return error instanceof ApiError && error.errorCode?.startsWith('PARAM_') === true
}

/** 判断是否为业务类错误（error_code 以 BIZ_ 开头） */
export function isBizError(error: unknown): boolean {
  return error instanceof ApiError && error.errorCode?.startsWith('BIZ_') === true
}

/** 判断是否为系统类错误（error_code 以 SYS_ 开头） */
export function isSysError(error: unknown): boolean {
  return error instanceof ApiError && error.errorCode?.startsWith('SYS_') === true
}
