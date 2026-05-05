import { parseResponse } from '@/lib/api-helpers'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import type { ApiResponse } from '@/types/api'

const API_BASE = '/api/webui/config/prompts'

export interface PromptFileInfo {
  name: string
  size: number
  modified_at: number
  display_name: string
  advanced: boolean
  description: string
}

export interface PromptCatalog {
  success: boolean
  languages: string[]
  files: Record<string, PromptFileInfo[]>
}

export interface PromptFileContent {
  success: boolean
  language: string
  filename: string
  content: string
}

export async function getPromptCatalog(): Promise<ApiResponse<PromptCatalog>> {
  const response = await fetchWithAuth(API_BASE)
  return parseResponse<PromptCatalog>(response)
}

export async function getPromptFile(
  language: string,
  filename: string
): Promise<ApiResponse<PromptFileContent>> {
  const response = await fetchWithAuth(`${API_BASE}/${encodeURIComponent(language)}/${encodeURIComponent(filename)}`)
  return parseResponse<PromptFileContent>(response)
}

export async function updatePromptFile(
  language: string,
  filename: string,
  content: string
): Promise<ApiResponse<PromptFileContent>> {
  const response = await fetchWithAuth(`${API_BASE}/${encodeURIComponent(language)}/${encodeURIComponent(filename)}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
  return parseResponse<PromptFileContent>(response)
}
