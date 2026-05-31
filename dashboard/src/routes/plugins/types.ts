import type { PluginInfo } from '@/types/plugin'
import type { PluginType } from '@/types/plugin'
import type { GitStatus, MaimaiVersion, PluginLoadProgress } from '@/lib/plugin-api'
import type { PluginStatsData } from '@/lib/plugin-stats'

export const PLUGIN_TYPE_LABELS: Record<PluginType, string> = {
  adapter: '适配器',
  tool: '工具',
  provider: '服务提供方',
  management: '管理',
  data: '数据',
  media: '媒体',
  game: '游戏娱乐',
  integration: '外部集成',
  extension: '通用扩展',
  other: '其他',
}

export const PLUGIN_TYPE_OPTIONS: Array<{ value: PluginType; label: string }> = [
  { value: 'adapter', label: PLUGIN_TYPE_LABELS.adapter },
  { value: 'tool', label: PLUGIN_TYPE_LABELS.tool },
  { value: 'provider', label: PLUGIN_TYPE_LABELS.provider },
  { value: 'management', label: PLUGIN_TYPE_LABELS.management },
  { value: 'data', label: PLUGIN_TYPE_LABELS.data },
  { value: 'media', label: PLUGIN_TYPE_LABELS.media },
  { value: 'game', label: PLUGIN_TYPE_LABELS.game },
  { value: 'integration', label: PLUGIN_TYPE_LABELS.integration },
  { value: 'extension', label: PLUGIN_TYPE_LABELS.extension },
  { value: 'other', label: PLUGIN_TYPE_LABELS.other },
]

export function getPluginType(plugin: { manifest?: { plugin_type?: PluginType } }): PluginType {
  return plugin.manifest?.plugin_type ?? 'extension'
}

export function getPluginTypeLabel(plugin: { manifest?: { plugin_type?: PluginType } }): string {
  return PLUGIN_TYPE_LABELS[getPluginType(plugin)]
}

// 导出类型
export type MarketplaceSortKey = 'default' | 'downloads' | 'likes' | 'rating'

export type { PluginInfo, PluginType, GitStatus, MaimaiVersion, PluginLoadProgress, PluginStatsData }
