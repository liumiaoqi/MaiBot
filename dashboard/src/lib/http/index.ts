/**
 * 请求客户端（ApiClient）统一出口。
 *
 * 业务 API 模块应从这里导入 backendApi / statsApi 与 ApiError，
 * 不要再直接使用 fetch / fetchWithAuth 手写请求样板。
 */
export { createApiClient } from './client'
export { ApiError, isAuthError, isBizError, isParamError, isSysError } from './errors'
export {
  isApiResponseEnvelope,
  isErrorResponseEnvelope,
  unwrapApiResponse,
} from './envelope'
export { authApi, backendApi, statsApi, STATS_SERVICE_BASE_URL } from './instances'
export type { ApiClient, ApiClientOptions, HttpMethod, QueryValue, RequestOptions } from './client'
export type { ApiResponseEnvelope, ErrorResponseEnvelope } from './envelope'
