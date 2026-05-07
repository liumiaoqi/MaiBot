import { parseResponse, throwIfError } from '@/lib/api-helpers'
import { resolveApiPath } from '@/lib/api-base'
import { fetchWithAuth } from '@/lib/fetch-with-auth'

const API_BASE = '/api/webui/reasoning-process'

export type ReasoningPromptFile = {
  stage: string
  session_id: string
  stem: string
  timestamp: number | null
  text_path: string | null
  html_path: string | null
  size: number
  modified_at: number
}

export type ReasoningPromptListResponse = {
  items: ReasoningPromptFile[]
  total: number
  page: number
  page_size: number
  stages: string[]
  sessions: string[]
}

export type ReasoningPromptContentResponse = {
  path: string
  content: string
  size: number
  modified_at: number
}

export type ReasoningPromptListParams = {
  stage?: string
  session?: string
  search?: string
  page?: number
  pageSize?: number
}

export async function listReasoningPromptFiles(
  params: ReasoningPromptListParams
): Promise<ReasoningPromptListResponse> {
  const queryParams = new URLSearchParams()
  queryParams.set('stage', params.stage ?? 'all')
  queryParams.set('session', params.session ?? 'all')
  queryParams.set('search', params.search ?? '')
  queryParams.set('page', String(params.page ?? 1))
  queryParams.set('page_size', String(params.pageSize ?? 50))

  const response = await fetchWithAuth(`${API_BASE}/files?${queryParams}`, { cache: 'no-store' })
  return throwIfError(await parseResponse<ReasoningPromptListResponse>(response))
}

export async function getReasoningPromptFile(
  path: string
): Promise<ReasoningPromptContentResponse> {
  const response = await fetchWithAuth(`${API_BASE}/file?path=${encodeURIComponent(path)}`, {
    cache: 'no-store',
  })
  return throwIfError(await parseResponse<ReasoningPromptContentResponse>(response))
}

export async function getReasoningPromptHtmlUrl(path: string): Promise<string> {
  return resolveApiPath(`${API_BASE}/html?path=${encodeURIComponent(path)}`)
}
