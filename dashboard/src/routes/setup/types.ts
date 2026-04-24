// 设置向导相关类型定义

export interface SetupStep {
  id: string
  title: string
  description: string
  icon: React.ComponentType<{ className?: string }>
}

// 步骤1：Bot基础信息
export interface BotBasicConfig {
  platform: string        // Primary platform name (normalized, lowercase)
  qq_account: number      // QQ account (preserved always for webui compat)
  platforms: string[]     // Other platform accounts "platform:account"
  nickname: string
  alias_names: string[]
}

// 步骤2：人格配置
export interface PersonalityConfig {
  personality: string
  reply_style: string
  multiple_reply_style: string[]
  multiple_probability: number
}

// 步骤3：表情包配置
export interface EmojiConfig {
  emoji_send_num: number
  max_reg_num: number
  do_replace: boolean
  check_interval: number
  steal_emoji: boolean
  content_filtration: boolean
  filtration_prompt: string
}

// 步骤4：其他基础配置
export interface OtherBasicConfig {
  all_global: boolean // 全局黑话模式（expression.all_global_jargon）
}

// 步骤5：硅基流动API配置
export interface SiliconFlowConfig {
  api_key: string
}
