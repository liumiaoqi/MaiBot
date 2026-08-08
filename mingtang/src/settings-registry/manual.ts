import type { SettingsRegistryEntry } from './settings-registry'
import { settingsRegistry } from './settings-registry'
import { menuItemsWithPath } from '@/app/layout/menu-sections'

/** Provider 表单字段（7 个）——route /config/model，routeParams { tab: 'providers' } */
const providerFields = [
  { name: 'name', label: '名称' },
  { name: 'base_url', label: 'API 地址' },
  { name: 'api_key', label: 'API 密钥' },
  { name: 'client_type', label: '客户端类型' },
  { name: 'max_retry', label: '最大重试' },
  { name: 'timeout', label: '超时时间' },
  { name: 'retry_interval', label: '重试间隔' },
]

/** Model 编辑字段（10 个）——route /config/model，routeParams { tab: 'models' } */
const modelEditFields = [
  { name: 'name', label: '模型名称' },
  { name: 'model_id', label: '模型 ID' },
  { name: 'provider', label: '提供者' },
  { name: 'max_tokens', label: '最大 Token' },
  { name: 'temperature', label: '温度' },
  { name: 'top_p', label: 'Top P' },
  { name: 'frequency_penalty', label: '频率惩罚' },
  { name: 'presence_penalty', label: '存在惩罚' },
  { name: 'context_length', label: '上下文长度' },
  { name: 'stream', label: '流式输出' },
]

/** 从菜单项构建手动条目 */
function buildMenuEntries(): SettingsRegistryEntry[] {
  return menuItemsWithPath.map((item, index) => ({
    id: `manual:page:${item.path}`,
    title: item.label,
    category: 'page',
    keywords: [
      item.label,
      ...(item.searchDescription ? [item.searchDescription] : []),
    ],
    route: item.path,
    description: item.searchDescription,
    source: 'manual' as const,
    order: index,
  }))
}

/** 从 Provider 字段构建手动条目 */
function buildProviderEntries(): SettingsRegistryEntry[] {
  return providerFields.map((field, index) => ({
    id: `manual:model:providers:${field.name}`,
    title: field.label,
    category: 'model',
    group: 'providers',
    keywords: [field.label, field.name],
    route: '/config/model',
    routeParams: { tab: 'providers' },
    fieldPath: field.name,
    source: 'manual' as const,
    order: index,
  }))
}

/** 从 Model 编辑字段构建手动条目 */
function buildModelEditEntries(): SettingsRegistryEntry[] {
  return modelEditFields.map((field, index) => ({
    id: `manual:model:models:${field.name}`,
    title: field.label,
    category: 'model',
    group: 'models',
    keywords: [field.label, field.name],
    route: '/config/model',
    routeParams: { tab: 'models' },
    fieldPath: field.name,
    source: 'manual' as const,
    order: index,
  }))
}

/** 手动登记——menuSections 页面项 + ProviderForm 字段 + ModelEdit 字段 */
export function registerManualEntries(): SettingsRegistryEntry[] {
  const entries = [
    ...buildMenuEntries(),
    ...buildProviderEntries(),
    ...buildModelEditEntries(),
  ]
  settingsRegistry.registerAll(entries)
  return entries
}