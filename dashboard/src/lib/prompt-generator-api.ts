import { parseResponse } from '@/lib/api-helpers'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import type { ApiResponse } from '@/types/api'

const PROMPT_GENERATOR_METHOD_NOT_ALLOWED_MESSAGE =
  '生成失败：可能是模型不支持或前后端版本不匹配，请换用文本聊天模型，或刷新并重启 WebUI 后再试。'

function normalizePromptGeneratorError<T>(result: ApiResponse<T>): ApiResponse<T> {
  if (result.success) {
    return result
  }

  const normalizedError = result.error.toLowerCase()
  if (normalizedError.includes('method not allowed') || normalizedError.includes('405')) {
    return {
      success: false,
      error: PROMPT_GENERATOR_METHOD_NOT_ALLOWED_MESSAGE,
    }
  }

  return result
}

export interface PromptGeneratorChatPrompt {
  platform: string
  item_id: string
  rule_type: string
  prompt: string
}

export interface PromptGeneratorConfigBlock {
  id: string
  section: string
  field: string
  title: string
  description: string
  value: unknown
  toml: string
}

export interface PromptGeneratorResult {
  personality: string
  reply_style: string
  multiple_reply_style: string[]
  group_chat_prompt: string
  private_chat_prompts: string
  chat_prompts: PromptGeneratorChatPrompt[]
  notes: string[]
}

export interface PromptGeneratorRequest {
  model_name: string
  source_text: string
  target_scene: string
  language: string
  extra_requirements: string
  temperature: number
  max_tokens: number
}

export interface PromptGeneratorResponse {
  success: boolean
  model_name: string
  result: PromptGeneratorResult
  config_blocks: PromptGeneratorConfigBlock[]
  toml_snippet: string
  raw_response: string
  reasoning: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export async function generatePromptPersona(
  payload: PromptGeneratorRequest
): Promise<ApiResponse<PromptGeneratorResponse>> {
  const response = await fetchWithAuth('/api/webui/config/prompt-generator/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return normalizePromptGeneratorError(await parseResponse<PromptGeneratorResponse>(response))
}

export interface PromptGeneratorApplyResponse {
  success: boolean
  message: string
  applied_blocks: number
  sections: string[]
}

export async function applyPromptGeneratorBlocks(
  blocks: PromptGeneratorConfigBlock[]
): Promise<ApiResponse<PromptGeneratorApplyResponse>> {
  const response = await fetchWithAuth('/api/webui/config/prompt-generator/apply', {
    method: 'POST',
    body: JSON.stringify({ blocks }),
  })
  return parseResponse<PromptGeneratorApplyResponse>(response)
}
