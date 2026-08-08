/**
 * 人物信息管理 API
 *
 * 请求样板（认证、解析、错误格式化）由 @/lib/http 的请求客户端承担；
 * 本文件只声明 endpoint 与业务错误文案。
 * 已切换为 throw 契约：成功直接返回数据，失败抛出 ApiError（配合 TanStack Query 使用）。
 */
import { ApiError, backendApi } from '@/lib/http'
import type {
  PersonDeleteResponse,
  PersonDetailResponse,
  PersonInfo,
  PersonListResponse,
  PersonStats,
  PersonStatsResponse,
  PersonUpdateRequest,
  PersonUpdateResponse,
} from '@/types/person'

const API_BASE = '/api/webui/person'

export interface PersonListData {
  data: PersonInfo[]
  total: number
  page: number
  page_size: number
}

export async function getPersonList(params: {
  page?: number
  page_size?: number
  search?: string
  is_known?: boolean
  platform?: string
}): Promise<PersonListData> {
  const data = await backendApi.get<PersonListResponse>(`${API_BASE}/list`, {
    query: {
      page: params.page || undefined,
      page_size: params.page_size || undefined,
      search: params.search || undefined,
      is_known: params.is_known,
      platform: params.platform || undefined,
    },
    errorMessage: '获取人物列表失败',
  })
  return {
    data: data.data,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
  }
}

export async function getPersonDetail(personId: string): Promise<PersonInfo> {
  const data = await backendApi.get<PersonDetailResponse>(`${API_BASE}/${personId}`, {
    errorMessage: '获取人物详情失败',
  })
  return data.data
}

export async function updatePerson(
  personId: string,
  updateData: PersonUpdateRequest
): Promise<PersonInfo> {
  const responseData = await backendApi.patch<PersonUpdateResponse>(`${API_BASE}/${personId}`, {
    body: updateData,
    errorMessage: '更新人物信息失败',
  })
  if (!responseData.data) {
    throw new ApiError(responseData.message || '更新人物信息失败', { detail: responseData })
  }
  return responseData.data
}

export async function deletePerson(personId: string): Promise<void> {
  await backendApi.delete<PersonDeleteResponse>(`${API_BASE}/${personId}`, {
    errorMessage: '删除人物信息失败',
  })
}

export async function getPersonStats(): Promise<PersonStats> {
  const data = await backendApi.get<PersonStatsResponse>(`${API_BASE}/stats/summary`, {
    errorMessage: '获取统计数据失败',
  })
  return data.data
}

export async function batchDeletePersons(personIds: string[]): Promise<{
  message: string
  deleted_count: number
  failed_count: number
  failed_ids: string[]
}> {
  const data = await backendApi.post<{
    message: string
    deleted_count: number
    failed_count: number
    failed_ids: string[]
  }>(`${API_BASE}/batch/delete`, {
    body: { person_ids: personIds },
    errorMessage: '批量删除失败',
  })
  return {
    message: data.message,
    deleted_count: data.deleted_count,
    failed_count: data.failed_count,
    failed_ids: data.failed_ids,
  }
}
