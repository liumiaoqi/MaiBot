/**
 * marketplace 数据层——插件市场页 useQuery/useMutation 统一入口（R4 债清理 P1）。
 *
 * 取代旧版 index.tsx 内 130 行手写编排（localStorage 缓存读取 → ws 订阅 → Promise.all
 * 并发 4 个 API → merge 逻辑 → 统计刷新）。行为语义原样迁入：
 * - 5 个 useQuery：已安装列表 / 市场清单 / Git 状态 / 麦麦版本 / 统计汇总（缓存先展示、后台刷新）
 * - 4 个 useMutation：安装 / 卸载 / 更新 / 点赞（成功后失效已安装列表，合并列表派生自动更新）
 * - usePluginProgress：WebSocket 进度订阅独立 hook（fetch/install 进度 + fetch 失败）
 * - 视图逻辑回调（checkPluginCompatibility / needsUpdate / getStatusBadge / getIncompatibleReason）
 *   从旧父组件搬入，由本 hook 统一提供
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2 } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import {
  checkGitStatus,
  checkPluginInstalled,
  connectPluginProgressWebSocket,
  fetchPluginList,
  getCachedPluginList,
  getInstalledPluginVersion,
  getInstalledPlugins,
  getMaimaiVersion,
  installPlugin,
  isPluginCompatible,
  uninstallPlugin,
  updatePlugin,
  type InstalledPlugin,
} from '@/lib/plugin-api'
import {
  getCachedPluginStatsSummary,
  getPluginStatsSummary,
  likePlugin,
  recordPluginDownload,
  type PluginStatsData,
} from '@/lib/plugin-stats'
import type {
  GitStatus,
  MaimaiVersion,
  PluginInfo,
  PluginLoadProgress,
} from '@/features/plugin/shared/types'

// ---- 纯数据函数（从旧 index.tsx 原样搬入） ----

const resolvePluginStats = (
  plugin: PluginInfo,
  statsSummary: Record<string, PluginStatsData>
): PluginStatsData | undefined => {
  const statsIds = [
    plugin.manifest?.id,
  ].filter((id): id is string => Boolean(id))

  return statsIds.map(id => statsSummary[id]).find(Boolean)
}

const buildPluginStatsMap = (
  pluginList: PluginInfo[],
  statsSummary: Record<string, PluginStatsData>
): Record<string, PluginStatsData> => {
  const statsMap: Record<string, PluginStatsData> = {}

  for (const plugin of pluginList) {
    const stats = resolvePluginStats(plugin, statsSummary)
    if (!stats) {
      continue
    }

    const statsIds = [
      plugin.manifest?.id,
      stats.plugin_id,
    ].filter((id): id is string => Boolean(id))

    for (const statsId of statsIds) {
      statsMap[statsId] = stats
    }
  }

  return statsMap
}

// 市场清单 + 已安装列表合并：标记安装状态/版本，并补入本地安装但不在市场的插件
// （语义与旧版 mergeInstalledPluginInfo 完全一致——缓存/merge 语义原样迁入）
const mergeInstalledPluginInfo = (
  marketPlugins: PluginInfo[],
  installed: InstalledPlugin[]
): PluginInfo[] => {
  const mergedData = marketPlugins.map(plugin => {
    const installedPlugin = installed.find(item => item.id === plugin.id || item.manifest?.id === plugin.id)
    const isInstalled = Boolean(installedPlugin) || checkPluginInstalled(plugin.id, installed)
    const installedVersion = installedPlugin?.manifest?.version ?? getInstalledPluginVersion(plugin.id, installed)

    return {
      ...plugin,
      installed: isInstalled,
      installed_version: installedVersion,
    }
  })

  for (const installedPlugin of installed) {
    const installedManifestId = installedPlugin.manifest?.id
    const existsInMarket = mergedData.some(
      p => p.id === installedPlugin.id || p.id === installedManifestId || p.manifest?.id === installedPlugin.id
    )
    if (!existsInMarket && installedPlugin.manifest) {
      const urls = installedPlugin.manifest.urls as PluginInfo['manifest']['urls'] | undefined
      // 添加本地安装但不在市场的插件
      mergedData.push({
        id: installedPlugin.id,
        manifest: {
          manifest_version: installedPlugin.manifest.manifest_version || 1,
          id: installedPlugin.manifest.id || installedPlugin.id,
          name: installedPlugin.manifest.name,
          version: installedPlugin.manifest.version,
          description: installedPlugin.manifest.description || '',
          author: installedPlugin.manifest.author,
          license: installedPlugin.manifest.license || 'Unknown',
          host_application: installedPlugin.manifest.host_application,
          homepage_url: installedPlugin.manifest.homepage_url || urls?.homepage,
          repository_url: installedPlugin.manifest.repository_url || urls?.repository,
          urls,
          keywords: installedPlugin.manifest.keywords || [],
          plugin_type: installedPlugin.manifest.plugin_type || 'extension',
          display: installedPlugin.manifest.display,
          changelog: installedPlugin.manifest.changelog,
          default_locale: (installedPlugin.manifest.default_locale as string) || 'zh-CN',
          locales_path: installedPlugin.manifest.locales_path as string | undefined,
        },
        downloads: 0,
        rating: 0,
        review_count: 0,
        installed: true,
        installed_version: installedPlugin.manifest.version,
        source: 'local',
        changelog: installedPlugin.changelog ?? undefined,
        stats_ids: [installedPlugin.manifest.id].filter(Boolean) as string[],
        published_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })
    }
  }

  return mergedData
}

// ---- WebSocket 进度订阅独立 hook ----

/**
 * 插件加载进度订阅（fetch/install/uninstall/update 操作进度）。
 * 行为与旧版 index.tsx 内联订阅一致：success 后 2s 清除进度；fetch 失败记录 fetchError。
 */
export function usePluginProgress() {
  const [loadProgress, setLoadProgress] = useState<PluginLoadProgress | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)

  useEffect(() => {
    let unsubscribeProgress: (() => Promise<void>) | null = null
    let isUnmounted = false

    const progressSubscription = connectPluginProgressWebSocket(
      (progress) => {
        if (isUnmounted) return

        setLoadProgress(progress)

        // 如果加载完成，清除进度
        if (progress.stage === 'success') {
          setTimeout(() => {
            if (!isUnmounted) {
              setLoadProgress(null)
            }
          }, 2000)
        } else if (progress.stage === 'error' && progress.operation === 'fetch') {
          setFetchError(progress.error || '加载失败')
        }
      },
      (error) => {
        console.error('WebSocket error:', error)
        if (!isUnmounted) {
          toast.error('WebSocket 连接失败', {
            description: '无法实时显示加载进度',
          })
        }
      }
    )

    progressSubscription
      .then((unsubscribe) => {
        if (isUnmounted) {
          void unsubscribe()
          return unsubscribe
        }

        unsubscribeProgress = unsubscribe
        return unsubscribe
      })
      .catch((error) => {
        console.error('WebSocket subscribe error:', error)
        return null
      })

    return () => {
      isUnmounted = true
      if (unsubscribeProgress) {
        void unsubscribeProgress()
      }
    }
  }, [])

  return {
    loadProgress,
    fetchError,
    reportProgress: setLoadProgress,
  }
}

// ---- 市场页主数据 hook ----

export function useMarketplaceData() {
  const queryClient = useQueryClient()
  const { loadProgress, fetchError, reportProgress } = usePluginProgress()
  const [likingPluginIds, setLikingPluginIds] = useState<Set<string>>(() => new Set())

  // 运行时信息（Git 状态、麦麦版本、已安装列表）并行加载；
  // 原本失败时静默降级（不打断页面），故用 data ?? 默认值，不强制报错
  const [gitStatusQuery, maimaiVersionQuery, installedPluginsQuery] = useQueries({
    queries: [
      {
        queryKey: ['plugin-git-status'],
        queryFn: () => checkGitStatus(),
      },
      {
        queryKey: ['plugin-maimai-version'],
        queryFn: () => getMaimaiVersion(),
      },
      {
        queryKey: ['plugin-installed-list'],
        queryFn: () => getInstalledPlugins(),
      },
    ],
  })

  // 市场清单：lib 内部有 5min TTL 缓存 + localStorage 持久化；
  // placeholderData 先展示缓存（若有），后台刷新——与旧版「先缓存后并行拉取」行为等价
  const marketQuery = useQuery({
    queryKey: ['plugin-market-list'],
    queryFn: () => fetchPluginList(),
    placeholderData: () => getCachedPluginList() ?? undefined,
    retry: false,
  })

  // 统计汇总：缓存先展示、后台强制刷新（forceRefresh 语义保留——有缓存时走网络）
  const statsQuery = useQuery({
    queryKey: ['plugin-stats-summary'],
    queryFn: () => getPluginStatsSummary({ forceRefresh: Boolean(getCachedPluginStatsSummary()) }),
    placeholderData: () => getCachedPluginStatsSummary() ?? undefined,
    retry: false,
  })

  const gitStatus: GitStatus | null = gitStatusQuery.data ?? null
  const maimaiVersion: MaimaiVersion | null = maimaiVersionQuery.data ?? null
  // installed 直接取 query 数据（undefined 兜底移到 useMemo 内部——避免 ?? [] 每次渲染产生新引用破坏 memo）
  const installed = installedPluginsQuery.data

  // 市场 + 已安装合并（含本地独有插件）；由已安装列表 query 派生，写操作失效后自动更新
  const plugins = useMemo(
    () => mergeInstalledPluginInfo(marketQuery.data ?? [], installed ?? []),
    [marketQuery.data, installed]
  )

  // 统计映射（key 覆盖 manifest.id 与 stats.plugin_id）
  const pluginStats = useMemo(
    () => buildPluginStatsMap(plugins, statsQuery.data ?? {}),
    [plugins, statsQuery.data]
  )

  // 加载/错误状态：有缓存数据时不显示加载；错误优先取市场请求错误，其次 ws fetch 错误
  const loading = marketQuery.isPending && !marketQuery.data
  const marketError = marketQuery.isError
    ? (marketQuery.error instanceof Error ? marketQuery.error : null)
    : null
  const error = marketQuery.isError
    ? (marketQuery.error instanceof Error ? marketQuery.error.message : '加载失败')
    : fetchError

  // 任一写操作成功后，重新拉取已安装列表（前缀失效）——合并列表派生自该 query
  const invalidateInstalledPlugins = () =>
    queryClient.invalidateQueries({ queryKey: ['plugin-installed-list'] })

  // ---- 写操作 mutations（行为与旧版 handleInstall/handleUninstall/handleUpdate/handleLike 等价） ----

  // 安装插件（onMutate/onSuccess/onError 保留旧版手动 progress 上报；错误 toast 由本 mutation 呈现）
  const installMutation = useMutation({
    mutationFn: (vars: { plugin: PluginInfo; branch: string }) => {
      const repositoryUrl =
        vars.plugin.manifest.repository_url || vars.plugin.manifest.urls?.repository || ''
      return installPlugin(vars.plugin.id, repositoryUrl, vars.branch)
    },
    meta: { errorTitle: '安装失败', suppressErrorToast: true },
    onMutate: ({ plugin }) => {
      reportProgress({
        operation: 'install',
        stage: 'loading',
        progress: 0,
        message: `正在准备安装 ${plugin.manifest.name}`,
        plugin_id: plugin.id,
        total_plugins: 1,
        loaded_plugins: 0,
      })
    },
    onSuccess: (_data, vars) => {
      // 记录下载统计
      if (vars.plugin.manifest.id) {
        recordPluginDownload(vars.plugin.manifest.id).catch((err) => {
          console.warn('Failed to record download:', err)
        })
      }

      toast.success('安装成功', {
        description: `${vars.plugin.manifest.name} 已成功安装`,
      })
      reportProgress({
        operation: 'install',
        stage: 'success',
        progress: 100,
        message: `${vars.plugin.manifest.name} 已成功安装`,
        plugin_id: vars.plugin.id,
        total_plugins: 1,
        loaded_plugins: 1,
      })

      // 重新加载已安装插件列表（合并列表派生自动更新）
      invalidateInstalledPlugins()
    },
    onError: (error, vars) => {
      const errorMessage = error instanceof Error ? error.message : '未知错误'
      reportProgress({
        operation: 'install',
        stage: 'error',
        progress: 0,
        message: errorMessage,
        error: errorMessage,
        plugin_id: vars.plugin.id,
        total_plugins: 1,
        loaded_plugins: 0,
      })
      toast.error('安装失败', {
        description: errorMessage,
      })
    },
  })

  // 卸载插件
  const uninstallMutation = useMutation({
    mutationFn: (vars: { plugin: PluginInfo }) =>
      uninstallPlugin(vars.plugin.id),
    meta: { errorTitle: '卸载失败', suppressErrorToast: true },
    onSuccess: (_data, vars) => {
      toast.success('卸载成功', {
        description: `${vars.plugin.manifest.name} 已成功卸载`,
      })

      // 重新加载已安装插件列表
      invalidateInstalledPlugins()
    },
    onError: (error) => {
      toast.error('卸载失败', {
        description: error instanceof Error ? error.message : '未知错误',
      })
    },
  })

  // 更新插件
  const updateMutation = useMutation({
    mutationFn: (vars: { plugin: PluginInfo }) => {
      const repositoryUrl =
        vars.plugin.manifest.repository_url || vars.plugin.manifest.urls?.repository || ''
      return updatePlugin(vars.plugin.id, repositoryUrl, 'main')
    },
    meta: { errorTitle: '更新失败', suppressErrorToast: true },
    onSuccess: (data, vars) => {
      toast.success('更新成功', {
        description: `${vars.plugin.manifest.name} 已从 ${data.old_version} 更新到 ${data.new_version}`,
      })

      // 重新加载已安装插件列表
      invalidateInstalledPlugins()
    },
    onError: (error) => {
      toast.error('更新失败', {
        description: error instanceof Error ? error.message : '未知错误',
      })
    },
  })

  // 点赞（likingPluginIds 保留旧版并发点赞保护；成功后更新统计查询缓存）
  const likeMutation = useMutation({
    mutationFn: (vars: { plugin: PluginInfo }) =>
      likePlugin(vars.plugin.manifest?.id || vars.plugin.id),
    meta: { errorTitle: '点赞失败', suppressErrorToast: true },
    onMutate: (vars) => {
      setLikingPluginIds((currentIds) => {
        const nextIds = new Set(currentIds)
        nextIds.add(vars.plugin.manifest?.id || vars.plugin.id)
        return nextIds
      })
    },
    onSettled: (_data, _error, vars) => {
      setLikingPluginIds((currentIds) => {
        const nextIds = new Set(currentIds)
        nextIds.delete(vars.plugin.manifest?.id || vars.plugin.id)
        return nextIds
      })
    },
    onSuccess: (result, vars) => {
      const pluginId = vars.plugin.manifest?.id || vars.plugin.id
      if (!result.success) {
        toast.error('点赞失败', {
          description: result.error || '无法提交点赞',
        })
        return
      }

      // 更新统计查询缓存——与旧版 setPluginStats 逻辑一致
      queryClient.setQueryData<Record<string, PluginStatsData>>(
        ['plugin-stats-summary'],
        (currentStats) => {
          const currentPluginStats = currentStats?.[pluginId] ?? currentStats?.[vars.plugin.id] ?? {
            plugin_id: pluginId,
            likes: 0,
            dislikes: 0,
            downloads: vars.plugin.downloads ?? 0,
            rating: vars.plugin.rating ?? 0,
            rating_count: 0,
          }
          const nextPluginStats: PluginStatsData = {
            ...currentPluginStats,
            plugin_id: pluginId,
            likes: Number(result.likes ?? currentPluginStats.likes),
            dislikes: Number(result.dislikes ?? currentPluginStats.dislikes),
            liked: result.liked,
            disliked: result.disliked,
          }
          const nextStats = { ...(currentStats ?? {}) }
          const statsIds = [pluginId, vars.plugin.id, vars.plugin.manifest?.id, currentPluginStats.plugin_id]
            .filter((id): id is string => Boolean(id))

          for (const statsId of statsIds) {
            nextStats[statsId] = nextPluginStats
          }

          return nextStats
        }
      )
    },
    onError: () => {
      toast.error('点赞失败', {
        description: '无法提交点赞',
      })
    },
  })

  // ---- 视图逻辑（从旧父组件搬入——由 hook 统一提供） ----

  // 检查插件兼容性
  // 规则：
  // 1. manifest_version === 1 的插件在麦麦 >= 1.0.0 时一律视为不兼容（旧 manifest 已不再被宿主接受）；
  // 2. 否则若声明了 host_application 范围，则按版本范围判定。
  const checkPluginCompatibility = (plugin: PluginInfo): boolean => {
    if (!maimaiVersion) return true

    // manifest v1 在 1.0.0+ 麦麦上不再兼容
    const manifestVersion = plugin.manifest?.manifest_version ?? 1
    if (manifestVersion <= 1 && maimaiVersion.version_major >= 1) {
      return false
    }

    if (!plugin.manifest?.host_application) return true

    return isPluginCompatible(
      plugin.manifest.host_application.min_version,
      plugin.manifest.host_application.max_version,
      maimaiVersion
    )
  }

  // 不兼容原因（用于 UI 提示）
  const getIncompatibleReason = (plugin: PluginInfo): string | null => {
    if (!maimaiVersion) return null
    const manifestVersion = plugin.manifest?.manifest_version ?? 1
    if (manifestVersion <= 1 && maimaiVersion.version_major >= 1) {
      return `该插件使用旧版 manifest (v${manifestVersion})，已不被麦麦 ${maimaiVersion.version} 支持`
    }
    if (plugin.manifest?.host_application && !isPluginCompatible(
      plugin.manifest.host_application.min_version,
      plugin.manifest.host_application.max_version,
      maimaiVersion
    )) {
      const min = plugin.manifest.host_application.min_version || '未知'
      const max = plugin.manifest.host_application.max_version
      const range = max ? `${min} - ${max}` : `${min}+`
      return `不兼容当前版本 (需要 ${range}，当前 ${maimaiVersion.version})`
    }
    return null
  }

  // 检查是否需要更新（市场版本比已安装版本新）
  const needsUpdate = (plugin: PluginInfo): boolean => {
    if (!plugin.installed || !plugin.installed_version || !plugin.manifest?.version) {
      return false
    }
    // 不兼容的插件不允许更新
    if (!checkPluginCompatibility(plugin)) {
      return false
    }

    const installedVer = plugin.installed_version.trim()
    const marketVer = plugin.manifest.version.trim()

    if (installedVer === marketVer) return false

    const installedParts = installedVer.split('.').map(Number)
    const marketParts = marketVer.split('.').map(Number)

    // 比较主版本号、次版本号、修订号
    for (let i = 0; i < 3; i++) {
      if ((marketParts[i] || 0) > (installedParts[i] || 0)) {
        return true  // 市场版本更新
      } else if ((marketParts[i] || 0) < (installedParts[i] || 0)) {
        return false  // 本地版本更新
      }
    }

    return false
  }

  // 获取插件状态徽章
  const getStatusBadge = (plugin: PluginInfo): React.JSX.Element | null => {
    // 优先显示兼容性状态（已安装但不兼容也需要提示，避免用户误以为可继续更新）
    if (maimaiVersion && !checkPluginCompatibility(plugin)) {
      return (
        <Badge variant="destructive" className="gap-1">
          <AlertCircle className="h-3 w-3" />
          不兼容
        </Badge>
      )
    }

    if (plugin.installed) {
      // 版本比较：去除两边空格并进行比较
      const installedVer = plugin.installed_version?.trim()
      const marketVer = plugin.manifest.version?.trim()

      if (installedVer !== marketVer) {
        // 简单的版本比较：只有当市场版本比已安装版本新时才显示"可更新"
        // 如果本地版本更新（比如手动更新或市场数据过期），则显示"已安装"
        const installedParts = installedVer?.split('.').map(Number) || [0, 0, 0]
        const marketParts = marketVer?.split('.').map(Number) || [0, 0, 0]

        // 比较主版本号、次版本号、修订号
        for (let i = 0; i < 3; i++) {
          if ((marketParts[i] || 0) > (installedParts[i] || 0)) {
            // 市场版本更新
            return (
              // orange 语义色板（可更新状态——色板豁免）
              <Badge variant="outline" className="gap-1 text-orange-600 border-orange-600">
                <AlertCircle className="h-3 w-3" />
                可更新
              </Badge>
            )
          } else if ((marketParts[i] || 0) < (installedParts[i] || 0)) {
            // 本地版本更新
            break
          }
        }
      }

      return (
        <Badge variant="default" className="gap-1">
          <CheckCircle2 className="h-3 w-3" />
          已安装
        </Badge>
      )
    }
    return null
  }

  return {
    // 数据
    plugins,
    loading,
    error,
    marketError,
    gitStatus,
    maimaiVersion,
    pluginStats,
    loadProgress,
    likingPluginIds,
    // 写操作
    installMutation,
    uninstallMutation,
    updateMutation,
    likeMutation,
    // 视图逻辑
    checkPluginCompatibility,
    needsUpdate,
    getStatusBadge,
    getIncompatibleReason,
  }
}
