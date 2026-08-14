/**
 * use-plugin-filter —— 插件市场过滤逻辑统一入口（R4 债清理 P2）。
 *
 * 收编重复的 search/type/compat 过滤实现（P1 前 installed-tab/updates-tab/marketplace-tab
 * 各一份 + marketplace 页 getFilteredPluginCount 计数）——当前实际剩余两处：
 * marketplace-tab 的 matchedPlugins 过滤 + marketplace 页的计数徽标。
 *
 * 注意：本文件按任务清单命名为 use-plugin-filter.ts，但导出的是纯函数
 * （React 19 purity 规则下渲染期过滤应保持无副作用、无 hook 依赖——见代码注释习惯），
 * 不做成 hook。两个调用方输入形态不同（组件 props vs 页面 state），纯函数直接复用。
 */
import type { MaimaiVersion, PluginInfo } from '@/features/plugin/shared/types'
import { getPluginType } from '@/features/plugin/shared/types'

export interface PluginFilterOptions {
  searchQuery: string
  pluginTypeFilter: string
  /** 仅显示与当前麦麦版本兼容的插件 */
  showCompatibleOnly: boolean
  /** 隐藏已安装插件（对应「显示已安装」开关关闭） */
  hideInstalledPlugins: boolean
  maimaiVersion: MaimaiVersion | null
  checkPluginCompatibility: (plugin: PluginInfo) => boolean
}

/** 按搜索词 / 类型 / 兼容性过滤市场插件（不含排序——排序留在调用方） */
export function filterPlugins(plugins: PluginInfo[], options: PluginFilterOptions): PluginInfo[] {
  const {
    searchQuery,
    pluginTypeFilter,
    showCompatibleOnly,
    hideInstalledPlugins,
    maimaiVersion,
    checkPluginCompatibility,
  } = options
  const normalizedQuery = searchQuery.toLowerCase()

  return plugins.filter((plugin) => {
    // 跳过没有 manifest 的插件
    if (!plugin.manifest) {
      return false
    }

    // 全部插件只展示 plugin-repo 中存在的市场插件，本地独有插件只在「已安装」显示。
    if (plugin.source === 'local') {
      return false
    }

    if (hideInstalledPlugins && plugin.installed) {
      return false
    }

    // 搜索过滤
    const matchesSearch =
      searchQuery === '' ||
      plugin.manifest.name?.toLowerCase().includes(normalizedQuery) ||
      plugin.manifest.description?.toLowerCase().includes(normalizedQuery) ||
      (plugin.manifest.keywords &&
        plugin.manifest.keywords.some((keyword) => keyword.toLowerCase().includes(normalizedQuery)))

    // 类型过滤
    const matchesType = pluginTypeFilter === 'all' || getPluginType(plugin) === pluginTypeFilter

    // 兼容性过滤
    const matchesCompatibility =
      !showCompatibleOnly || !maimaiVersion || checkPluginCompatibility(plugin)

    return matchesSearch && matchesType && matchesCompatibility
  })
}

/** 过滤后的插件数量（页面计数徽标用） */
export function countFilteredPlugins(plugins: PluginInfo[], options: PluginFilterOptions): number {
  return filterPlugins(plugins, options).length
}
