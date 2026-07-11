/**
 * 响应包络类型与解包函数。
 *
 * 支持 SSD1 统一响应体格式：
 * - 成功：ApiResponseEnvelope<T>（{code, data, message}）
 * - 失败：ErrorResponseEnvelope（{error_code, error_message, details?}）
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
