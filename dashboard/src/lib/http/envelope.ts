/**
 * 响应包络类型与解包函数。
 *
 * 支持两种格式：
 * 1. SSD1 统一响应体 ApiResponseEnvelope<T>（{code, data, message}）—— 新格式
 * 2. 旧格式 SuccessEnvelope（{success, message?, data?}）—— 过渡期兼容
 *
 * 请求客户端自动检测格式并解包，API 模块层无需手动处理。
 */
import { ApiError } from './errors'

/** SSD1 后端统一成功响应体 */
export interface ApiResponseEnvelope<T> {
  code: number
  data: T
  message: string
}

/** SSD1 后端统一错误响应体 */
export interface ErrorResponseEnvelope {
  error_code: string
  error_message: string
  details?: unknown
}

/** 旧格式业务级响应包络（过渡期兼容，迁移完成后删除） */
export interface SuccessEnvelope {
  success: boolean
  message?: string
}

/** 类型守卫：判断响应体是否为 ApiResponse 格式 */
export function isApiResponseEnvelope(data: unknown): data is ApiResponseEnvelope<unknown> {
  return (
    data !== null &&
    typeof data === 'object' &&
    'code' in data &&
    typeof (data as ApiResponseEnvelope<unknown>).code === 'number'
  )
}

/** 类型守卫：判断错误体是否为 ErrorResponse 格式 */
export function isErrorResponseEnvelope(data: unknown): data is ErrorResponseEnvelope {
  return (
    data !== null &&
    typeof data === 'object' &&
    'error_code' in data &&
    typeof (data as ErrorResponseEnvelope).error_code === 'string'
  )
}

/** 解包 ApiResponse：code === 0 时提取 data，code !== 0 时抛出 ApiError */
export function unwrapApiResponse<T>(data: ApiResponseEnvelope<T>, fallback: string): T {
  if (data.code !== 0) {
    throw new ApiError(data.message || fallback, { detail: data })
  }
  return data.data
}

/** 校验旧格式响应体中的业务级 success 标记，失败时抛出 ApiError（过渡期兼容） */
export function requireSuccess<T extends SuccessEnvelope>(data: T, fallback: string): T {
  if (!data.success) {
    throw new ApiError(data.message || fallback, { detail: data })
  }
  return data
}
