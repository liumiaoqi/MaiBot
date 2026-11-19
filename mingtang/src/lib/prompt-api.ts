import { backendApi } from '@/lib/http'
import type {
  PromptCatalog,
  PromptFileContent,
  PromptFileInfo,
  PromptValidationResult,
  PromptVersionInfo,
} from '@/lib/contract'

const API_BASE = '/api/webui/config/prompts'

export type {
  PromptCatalog,
  PromptFileContent,
  PromptFileInfo,
  PromptValidationResult,
  PromptVersionInfo,
}

export interface PromptUpdateOptions {
  versionId?: string | null
  label?: string
  createVersion?: boolean
}

export async function getPromptCatalog(): Promise<PromptCatalog> {
  return backendApi.get<PromptCatalog>(API_BASE, {
    errorMessage: '获取 Prompt 文件列表失败',
  })
}

export async function getPromptFile(
  language: string,
  filename: string
): Promise<PromptFileContent> {
  return backendApi.get<PromptFileContent>(
    `${API_BASE}/${encodeURIComponent(language)}/${encodeURIComponent(filename)}`,
    {
      errorMessage: '获取 Prompt 文件失败',
    }
  )
}

export async function getDefaultPromptFile(
  language: string,
  filename: string
): Promise<PromptFileContent> {
  return backendApi.get<PromptFileContent>(
    `${API_BASE}/${encodeURIComponent(language)}/${encodeURIComponent(filename)}/default`,
    {
      errorMessage: '获取默认 Prompt 文件失败',
    }
  )
}

export async function updatePromptFile(
  language: string,
  filename: string,
  content: string,
  options: PromptUpdateOptions = {}
): Promise<PromptFileContent> {
  return backendApi.put<PromptFileContent>(
    `${API_BASE}/${encodeURIComponent(language)}/${encodeURIComponent(filename)}`,
    {
      body: {
        content,
        version_id: options.versionId,
        label: options.label ?? '',
        create_version: options.createVersion ?? false,
      },
      errorMessage: '保存 Prompt 文件失败',
    }
  )
}

export async function resetPromptFile(
  language: string,
  filename: string
): Promise<PromptFileContent> {
  return backendApi.delete<PromptFileContent>(
    `${API_BASE}/${encodeURIComponent(language)}/${encodeURIComponent(filename)}`,
    {
      errorMessage: '重置 Prompt 文件失败',
    }
  )
}

export async function getPromptVersionFile(
  language: string,
  filename: string,
  versionId: string
): Promise<PromptFileContent> {
  return backendApi.get<PromptFileContent>(
    `${API_BASE}/${encodeURIComponent(language)}/${encodeURIComponent(filename)}/versions/${encodeURIComponent(versionId)}`,
    {
      errorMessage: '获取 Prompt 版本失败',
    }
  )
}

export async function activatePromptVersion(
  language: string,
  filename: string,
  versionId: string
): Promise<PromptFileContent> {
  return backendApi.post<PromptFileContent>(
    `${API_BASE}/${encodeURIComponent(language)}/${encodeURIComponent(filename)}/versions/${encodeURIComponent(versionId)}/activate`,
    {
      errorMessage: '启用 Prompt 版本失败',
    }
  )
}
