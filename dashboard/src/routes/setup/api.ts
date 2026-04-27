// 设置向导API调用函数

import { parseResponse, throwIfError } from '@/lib/api-helpers'
import { fetchWithAuth, getAuthHeaders } from '@/lib/fetch-with-auth'

import type {
  BotBasicConfig,
  EmojiConfig,
  OtherBasicConfig,
  PersonalityConfig,
  SiliconFlowConfig,
} from './types'

// ===== 读取配置 =====

// 读取Bot基础配置
export async function loadBotBasicConfig(): Promise<BotBasicConfig> {
  const response = await fetchWithAuth('/api/webui/config/bot', {
    method: 'GET',
    headers: getAuthHeaders(),
  })

  const result = await parseResponse<{ config: { bot?: BotBasicConfig } }>(
    response
  )
  const data = throwIfError(result)
  const botConfig = (data.config.bot || {}) as Partial<BotBasicConfig>

  return {
    platform: botConfig.platform || (botConfig.qq_account ? 'qq' : ''),
    qq_account: botConfig.qq_account || 0,
    platforms: botConfig.platforms || [],
    nickname: botConfig.nickname || '',
    alias_names: botConfig.alias_names || [],
  }
}

// 读取人格配置
export async function loadPersonalityConfig(): Promise<PersonalityConfig> {
  const response = await fetchWithAuth('/api/webui/config/bot', {
    method: 'GET',
    headers: getAuthHeaders(),
  })

  const result = await parseResponse<{
    config: { personality?: PersonalityConfig }
  }>(response)
  const data = throwIfError(result)
  const personalityConfig = (data.config.personality || {}) as Partial<PersonalityConfig>

  return {
    personality: personalityConfig.personality || '',
    reply_style: personalityConfig.reply_style || '',
    multiple_reply_style: personalityConfig.multiple_reply_style || [],
    multiple_probability: personalityConfig.multiple_probability ?? 0.2,
  }
}

// 读取表情包配置
export async function loadEmojiConfig(): Promise<EmojiConfig> {
  const response = await fetchWithAuth('/api/webui/config/bot', {
    method: 'GET',
    headers: getAuthHeaders(),
  })

  const result = await parseResponse<{ config: { emoji?: EmojiConfig } }>(
    response
  )
  const data = throwIfError(result)
  const emojiConfig = (data.config.emoji || {}) as Partial<EmojiConfig>

  return {
    emoji_send_num: emojiConfig.emoji_send_num ?? 25,
    max_reg_num: emojiConfig.max_reg_num ?? 64,
    do_replace: emojiConfig.do_replace ?? true,
    check_interval: emojiConfig.check_interval ?? 10,
    steal_emoji: emojiConfig.steal_emoji ?? true,
    content_filtration: emojiConfig.content_filtration ?? false,
    filtration_prompt: emojiConfig.filtration_prompt || '',
  }
}

// 读取其他基础配置
export async function loadOtherBasicConfig(): Promise<OtherBasicConfig> {
  const response = await fetchWithAuth('/api/webui/config/bot', {
    method: 'GET',
    headers: getAuthHeaders(),
  })

  const result = await parseResponse<{
    config: {
      expression?: { all_global_jargon?: boolean }
    }
  }>(response)
  const data = throwIfError(result)
  const config = data.config

  const expressionConfig = config.expression || {}

  return {
    all_global: expressionConfig.all_global_jargon ?? true,
  }
}

// 读取硅基流动API配置
export async function loadSiliconFlowConfig(): Promise<SiliconFlowConfig> {
  const response = await fetchWithAuth('/api/webui/config/model', {
    method: 'GET',
    headers: getAuthHeaders(),
  })

  const result = await parseResponse<{
    config: {
      api_providers?: Array<{ name: string; api_key?: string }>
    }
  }>(response)
  const data = throwIfError(result)
  const modelConfig = data.config

  // 获取SiliconFlow提供商的API Key
  const apiProviders = modelConfig.api_providers || []
  const siliconFlowProvider = apiProviders.find((p) => p.name === 'SiliconFlow')

  return {
    api_key: siliconFlowProvider?.api_key || '',
  }
}

// ===== 保存配置 =====

// 保存Bot基础配置
export async function saveBotBasicConfig(config: BotBasicConfig) {
  const response = await fetchWithAuth('/api/webui/config/bot/section/bot', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(config),
  })

  const result = await parseResponse(response)
  return throwIfError(result)
}

// 保存人格配置
export async function savePersonalityConfig(config: PersonalityConfig) {
  const response = await fetchWithAuth('/api/webui/config/bot/section/personality', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(config),
    }
  )

  const result = await parseResponse(response)
  return throwIfError(result)
}

// 保存表情包配置
export async function saveEmojiConfig(config: EmojiConfig) {
  const response = await fetchWithAuth('/api/webui/config/bot/section/emoji', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(config),
  })

  const result = await parseResponse(response)
  return throwIfError(result)
}

// 保存其他基础配置（黑话）
export async function saveOtherBasicConfig(config: OtherBasicConfig) {
  const response = await fetchWithAuth('/api/webui/config/bot/section/expression', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ all_global_jargon: config.all_global }),
  })

  const result = await parseResponse(response)
  return throwIfError(result)
}

// 保存硅基流动API配置
export async function saveSiliconFlowConfig(config: SiliconFlowConfig) {
  // 1. 读取现有配置
  const response = await fetchWithAuth('/api/webui/config/model', {
    method: 'GET',
    headers: getAuthHeaders(),
  })

  const result = await parseResponse<{
    config: {
      api_providers?: Array<Record<string, unknown>>
    }
  }>(response)
  const currentModelConfig = throwIfError(result)
  const modelConfig = currentModelConfig.config

  // 2. 更新SiliconFlow提供商的API Key
  const apiProviders = modelConfig.api_providers || []
  const siliconFlowIndex = apiProviders.findIndex((p) => p.name === 'SiliconFlow')

  if (siliconFlowIndex >= 0) {
    // 更新现有提供商的API Key
    apiProviders[siliconFlowIndex] = {
      ...apiProviders[siliconFlowIndex],
      api_key: config.api_key,
    }
  } else {
    // 如果不存在,创建新的SiliconFlow提供商
    apiProviders.push({
      name: 'SiliconFlow',
      base_url: 'https://api.siliconflow.cn/v1',
      api_key: config.api_key,
      client_type: 'openai',
      max_retry: 3,
      timeout: 120,
      retry_interval: 5,
    })
  }

  // 3. 保存更新后的配置
  const updatedConfig = {
    ...modelConfig,
    api_providers: apiProviders,
  }

  const saveResponse = await fetchWithAuth('/api/webui/config/model', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(updatedConfig),
  })

  const saveResult = await parseResponse(saveResponse)
  return throwIfError(saveResult)
}

// 标记设置完成
export async function completeSetup() {
  const response = await fetchWithAuth('/api/webui/setup/complete', {
    method: 'POST',
  })

  const result = await parseResponse(response)
  return throwIfError(result)
}
