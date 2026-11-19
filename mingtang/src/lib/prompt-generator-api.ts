import { ApiError, backendApi } from '@/lib/http'
import type {
  PromptGeneratorApplyResponse,
  PromptGeneratorChatPrompt,
  PromptGeneratorConfigBlock,
  PromptGeneratorRequest,
  PromptGeneratorResponse,
  PromptGeneratorResult,
} from '@/lib/contract'

const PROMPT_GENERATOR_METHOD_NOT_ALLOWED_MESSAGE =
  '生成失败：可能是模型不支持或前后端版本不匹配，请换用文本聊天模型，或刷新并重启 WebUI 后再试。'

// 把 405/method not allowed 这类底层错误归一化为对用户更友好的提示后重新抛出
function normalizePromptGeneratorError(error: unknown): never {
  if (error instanceof ApiError) {
    const normalizedError = error.message.toLowerCase()
    if (normalizedError.includes('method not allowed') || normalizedError.includes('405')) {
      throw new ApiError(PROMPT_GENERATOR_METHOD_NOT_ALLOWED_MESSAGE)
    }
  }
  throw error
}

export type {
  PromptGeneratorApplyResponse,
  PromptGeneratorChatPrompt,
  PromptGeneratorConfigBlock,
  PromptGeneratorRequest,
  PromptGeneratorResponse,
  PromptGeneratorResult,
}

export async function generatePromptPersona(
  payload: PromptGeneratorRequest
): Promise<PromptGeneratorResponse> {
  try {
    return await backendApi.post<PromptGeneratorResponse>('/api/webui/config/prompt-generator/generate', {
      body: payload,
      errorMessage: '生成人设 Prompt 失败',
    })
  } catch (error) {
    normalizePromptGeneratorError(error)
  }
}


export async function applyPromptGeneratorBlocks(
  blocks: PromptGeneratorConfigBlock[]
): Promise<PromptGeneratorApplyResponse> {
  return backendApi.post<PromptGeneratorApplyResponse>('/api/webui/config/prompt-generator/apply', {
    body: { blocks },
    errorMessage: '应用生成结果失败',
  })
}
