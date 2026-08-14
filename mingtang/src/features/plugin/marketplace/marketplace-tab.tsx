import { useState } from 'react'

import type {
  MarketplaceSortKey,
  PluginInfo,
  PluginStatsData,
} from '@/features/plugin/shared/types'

import { PluginCard, type PluginCardProps } from './plugin-card'
import { filterPlugins } from './use-plugin-filter'

const SURPRISE_PLUGIN_COUNT = 4
const SURPRISE_CANDIDATE_LIMIT = 20
const FRESHNESS_BOOST_WEIGHT = 4
const FRESHNESS_BOOST_WINDOW_DAYS = 120
const LAUNCH_BOOST_WEIGHT = 12
const LAUNCH_BOOST_FULL_HOURS = 24
const LAUNCH_BOOST_DECAY_HOURS = 48
const MS_PER_DAY = 24 * 60 * 60 * 1000
const MS_PER_HOUR = 60 * 60 * 1000

interface MarketplaceScoreBasis {
  maxDownloadScore: number
  maxLikeScore: number
  maxRatingScore: number
  maxMarketplaceOrder: number
}

// MarketplaceTabProps：卡片相关回调/数据从 PluginCardProps 经 ts Pick 派生单一来源
// （R4 债清理 P2——避免 16-prop 接口多处重复声明）
interface MarketplaceTabProps extends Pick<
  PluginCardProps,
  | 'gitStatus'
  | 'maimaiVersion'
  | 'pluginStats'
  | 'loadProgress'
  | 'likingPluginIds'
  | 'onInstall'
  | 'onLike'
  | 'onUpdate'
  | 'onUninstall'
  | 'onDetail'
  | 'checkPluginCompatibility'
  | 'needsUpdate'
  | 'getStatusBadge'
  | 'getIncompatibleReason'
> {
  plugins: PluginInfo[]
  searchQuery: string
  pluginTypeFilter: string
  showCompatibleOnly: boolean
  hideInstalledPlugins: boolean
  sortBy: MarketplaceSortKey
}

function getPluginIdentity(plugin: PluginInfo): string {
  return plugin.manifest?.id || plugin.id || plugin.marketplace_id || plugin.manifest?.name
}

function parsePluginTime(value: string | undefined): number {
  if (!value) {
    return 0
  }

  const time = Date.parse(value)
  return Number.isNaN(time) ? 0 : time
}

function getPluginFreshness(plugin: PluginInfo): number {
  const publishedTime = parsePluginTime(plugin.published_at)
  if (publishedTime > 0) {
    return publishedTime
  }

  const updatedTime = parsePluginTime(plugin.updated_at)
  if (updatedTime > 0) {
    return updatedTime
  }

  return plugin.marketplace_order ?? 0
}

function getFreshnessBoost(plugin: PluginInfo, maxMarketplaceOrder: number, now: number): number {
  const publishedTime = parsePluginTime(plugin.published_at)
  const updatedTime = parsePluginTime(plugin.updated_at)
  const pluginTime = publishedTime > 0 ? publishedTime : updatedTime

  if (pluginTime > 0) {
    const ageDays = Math.max(0, (now - pluginTime) / MS_PER_DAY)
    if (ageDays >= FRESHNESS_BOOST_WINDOW_DAYS) {
      return 0
    }

    return (1 - ageDays / FRESHNESS_BOOST_WINDOW_DAYS) * FRESHNESS_BOOST_WEIGHT
  }

  if (maxMarketplaceOrder <= 0) {
    return 0
  }

  return ((plugin.marketplace_order ?? 0) / maxMarketplaceOrder) * FRESHNESS_BOOST_WEIGHT
}

function getLaunchBoost(plugin: PluginInfo, now: number): number {
  const publishedTime = parsePluginTime(plugin.published_at)
  const updatedTime = parsePluginTime(plugin.updated_at)
  const pluginTime = publishedTime > 0 ? publishedTime : updatedTime

  if (pluginTime <= 0) {
    return 0
  }

  const ageHours = Math.max(0, (now - pluginTime) / MS_PER_HOUR)
  if (ageHours <= LAUNCH_BOOST_FULL_HOURS) {
    return LAUNCH_BOOST_WEIGHT
  }
  if (ageHours >= LAUNCH_BOOST_DECAY_HOURS) {
    return 0
  }

  const decayProgress =
    (ageHours - LAUNCH_BOOST_FULL_HOURS) / (LAUNCH_BOOST_DECAY_HOURS - LAUNCH_BOOST_FULL_HOURS)
  return (1 - decayProgress) * LAUNCH_BOOST_WEIGHT
}

function normalizeScore(value: number, maxValue: number, weight: number): number {
  if (maxValue <= 0) {
    return 0
  }

  return (value / maxValue) * weight
}

function getStableRandomRank(seed: string, plugin: PluginInfo): number {
  const value = `${seed}:${getPluginIdentity(plugin)}`
  let hash = 2166136261

  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }

  return hash >>> 0
}

function selectSurprisePlugins(
  plugins: PluginInfo[],
  sortBy: MarketplaceSortKey,
  seed: string
): PluginInfo[] {
  if (sortBy !== 'default' || plugins.length <= SURPRISE_PLUGIN_COUNT) {
    return []
  }

  const candidateCount = Math.min(
    SURPRISE_CANDIDATE_LIMIT,
    Math.max(SURPRISE_PLUGIN_COUNT, Math.ceil(plugins.length * 0.3))
  )

  return [...plugins]
    .sort((left, right) => {
      const freshnessDiff = getPluginFreshness(right) - getPluginFreshness(left)
      if (freshnessDiff !== 0) {
        return freshnessDiff
      }

      return (right.marketplace_order ?? 0) - (left.marketplace_order ?? 0)
    })
    .slice(0, candidateCount)
    .sort((left, right) => getStableRandomRank(seed, left) - getStableRandomRank(seed, right))
    .slice(0, SURPRISE_PLUGIN_COUNT)
}

export function MarketplaceTab({
  plugins,
  searchQuery,
  pluginTypeFilter,
  showCompatibleOnly,
  hideInstalledPlugins,
  sortBy,
  gitStatus,
  maimaiVersion,
  pluginStats,
  loadProgress,
  likingPluginIds,
  onInstall,
  onLike,
  onUpdate,
  onUninstall,
  onDetail,
  checkPluginCompatibility,
  needsUpdate,
  getStatusBadge,
  getIncompatibleReason,
}: MarketplaceTabProps) {
  // surpriseSeed/renderTime 在 useState 初始化器中调用 Math.random/Date.now——
  // React 19 purity 规则禁止渲染期调用，但初始化器仅首次渲染执行一次（lazy init），
  // 属于"派生到 effect/事件"的合规变体（搬移清单 §一.2 purity 例外）
  const [surpriseSeed] = useState(() => Math.random().toString(36).slice(2))
  const [renderTime] = useState(() => Date.now())

  // 过滤插件
  const getPluginStats = (plugin: PluginInfo): PluginStatsData | undefined => {
    const statsIds = [plugin.manifest?.id, plugin.id].filter((id): id is string => Boolean(id))

    return statsIds.map((id) => pluginStats[id]).find(Boolean)
  }

  const getSortValue = (
    plugin: PluginInfo,
    scoreBasis: MarketplaceScoreBasis,
    now: number
  ): number => {
    const stats = getPluginStats(plugin)

    if (sortBy === 'default') {
      const downloads = stats?.downloads ?? plugin.downloads ?? 0
      const likes = stats?.likes ?? 0
      const rating = stats?.rating ?? plugin.rating ?? 0
      const ratingCount = stats?.rating_count ?? 0
      const downloadScore = Math.log10(downloads + 1)
      const likeScore = Math.log10(likes + 1)
      const ratingScore = rating * Math.log10(ratingCount + 2)

      return (
        normalizeScore(downloadScore, scoreBasis.maxDownloadScore, 4) +
        normalizeScore(likeScore, scoreBasis.maxLikeScore, 3) +
        normalizeScore(ratingScore, scoreBasis.maxRatingScore, 2) +
        getLaunchBoost(plugin, now) +
        getFreshnessBoost(plugin, scoreBasis.maxMarketplaceOrder, now)
      )
    }
    if (sortBy === 'latest') {
      return getPluginFreshness(plugin)
    }
    if (sortBy === 'downloads') {
      return stats?.downloads ?? plugin.downloads ?? 0
    }
    if (sortBy === 'likes') {
      return stats?.likes ?? 0
    }
    if (sortBy === 'rating') {
      return stats?.rating ?? plugin.rating ?? 0
    }

    return 0
  }

  // 搜索/类型/兼容性过滤——统一走 use-plugin-filter 纯函数（R4 债清理 P2）
  const matchedPlugins = filterPlugins(plugins, {
    searchQuery,
    pluginTypeFilter,
    showCompatibleOnly,
    hideInstalledPlugins,
    maimaiVersion,
    checkPluginCompatibility,
  })
  const scoreBasis = matchedPlugins.reduce<MarketplaceScoreBasis>(
    (basis, plugin) => {
      const stats = getPluginStats(plugin)
      const downloads = stats?.downloads ?? plugin.downloads ?? 0
      const likes = stats?.likes ?? 0
      const rating = stats?.rating ?? plugin.rating ?? 0
      const ratingCount = stats?.rating_count ?? 0

      return {
        maxDownloadScore: Math.max(basis.maxDownloadScore, Math.log10(downloads + 1)),
        maxLikeScore: Math.max(basis.maxLikeScore, Math.log10(likes + 1)),
        maxRatingScore: Math.max(basis.maxRatingScore, rating * Math.log10(ratingCount + 2)),
        maxMarketplaceOrder: Math.max(basis.maxMarketplaceOrder, plugin.marketplace_order ?? 0),
      }
    },
    {
      maxDownloadScore: 0,
      maxLikeScore: 0,
      maxRatingScore: 0,
      maxMarketplaceOrder: 0,
    }
  )
  const now = renderTime
  const filteredPlugins = matchedPlugins.sort((left, right) => {
    const valueDiff = getSortValue(right, scoreBasis, now) - getSortValue(left, scoreBasis, now)
    if (valueDiff !== 0) {
      return valueDiff
    }

    const freshnessDiff = getPluginFreshness(right) - getPluginFreshness(left)
    if (freshnessDiff !== 0) {
      return freshnessDiff
    }

    return (left.manifest?.name || left.id).localeCompare(right.manifest?.name || right.id)
  })

  const surprisePlugins = selectSurprisePlugins(filteredPlugins, sortBy, surpriseSeed)
  const surprisePluginIds = new Set(surprisePlugins.map(getPluginIdentity))
  const mainPlugins = filteredPlugins.filter(
    (plugin) => !surprisePluginIds.has(getPluginIdentity(plugin))
  )
  const displayPlugins = [...surprisePlugins, ...mainPlugins]

  const renderPluginCard = (plugin: PluginInfo) => (
    <PluginCard
      key={plugin.id}
      plugin={plugin}
      gitStatus={gitStatus}
      maimaiVersion={maimaiVersion}
      pluginStats={pluginStats}
      loadProgress={loadProgress}
      likingPluginIds={likingPluginIds}
      onInstall={onInstall}
      onLike={onLike}
      onUpdate={onUpdate}
      onUninstall={onUninstall}
      onDetail={onDetail}
      checkPluginCompatibility={checkPluginCompatibility}
      needsUpdate={needsUpdate}
      getStatusBadge={getStatusBadge}
      getIncompatibleReason={getIncompatibleReason}
    />
  )

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 2xl:grid-cols-4">
      {displayPlugins.map(renderPluginCard)}
    </div>
  )
}