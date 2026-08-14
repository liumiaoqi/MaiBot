/**
 * plugin-marketplace 市场页——视图层。
 *
 * R4 债清理 P1：130 行手写编排（缓存读取 / ws 订阅 / Promise.all / merge / 统计刷新）、
 * 死状态（setInstalledPlugins）与视图逻辑回调（getStatusBadge / needsUpdate /
 * checkPluginCompatibility / getIncompatibleReason）已下沉到 hooks/use-marketplace-data.ts；
 * 本文件只保留页面壳、视图状态（搜索/筛选/排序/对话框）与事件接线。
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { AlertTriangle, ArrowUpDown, Filter, Info, Loader2, Search, Settings2 } from 'lucide-react'
import { toast } from 'sonner'

import { RestartOverlay } from '@/components/restart-overlay'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ThinkingIllustration } from '@/components/ui/thinking-illustration'
import { RestartProvider } from '@/lib/restart-context'
import { PluginDetailPage } from '@/features/plugin/detail'
import type { MarketplaceSortKey, PluginInfo } from '@/features/plugin/shared/types'
import { PLUGIN_TYPE_OPTIONS } from '@/features/plugin/shared/types'

import { PLUGIN_MARKET_COMPATIBLE_ONLY_KEY } from './constants'
import { InstallDialog } from './install-dialog'
import { MarketplaceTab } from './marketplace-tab'
import { countFilteredPlugins } from './use-plugin-filter'
import { useMarketplaceData } from './hooks/use-marketplace-data'

const PLUGIN_MARKET_VIEW_STATE_KEY = 'plugins-market-view-state'
const PLUGIN_MARKET_SCROLL_TOP_KEY = 'plugins-market-scroll-top'
const MARKETPLACE_SORT_KEYS: MarketplaceSortKey[] = ['default', 'latest', 'downloads', 'likes', 'rating']

interface PluginMarketplaceViewState {
  searchQuery: string
  pluginTypeFilter: string
  marketplaceSortBy: MarketplaceSortKey
  showInstalledPlugins: boolean
}

const DEFAULT_PLUGIN_MARKET_VIEW_STATE: PluginMarketplaceViewState = {
  searchQuery: '',
  pluginTypeFilter: 'all',
  marketplaceSortBy: 'default',
  showInstalledPlugins: false,
}

interface PluginMarketplacePageProps {
  embedded?: boolean
}

const readPluginMarketplaceViewState = (): PluginMarketplaceViewState => {
  const savedState = sessionStorage.getItem(PLUGIN_MARKET_VIEW_STATE_KEY)
  if (!savedState) {
    return DEFAULT_PLUGIN_MARKET_VIEW_STATE
  }

  const parsed = JSON.parse(savedState) as Partial<PluginMarketplaceViewState>
  const pluginTypeFilter = typeof parsed.pluginTypeFilter === 'string'
    && (parsed.pluginTypeFilter === 'all' || PLUGIN_TYPE_OPTIONS.some(option => option.value === parsed.pluginTypeFilter))
    ? parsed.pluginTypeFilter
    : DEFAULT_PLUGIN_MARKET_VIEW_STATE.pluginTypeFilter
  const marketplaceSortBy = parsed.marketplaceSortBy
    && MARKETPLACE_SORT_KEYS.includes(parsed.marketplaceSortBy)
    ? parsed.marketplaceSortBy
    : DEFAULT_PLUGIN_MARKET_VIEW_STATE.marketplaceSortBy

  return {
    searchQuery: typeof parsed.searchQuery === 'string'
      ? parsed.searchQuery
      : DEFAULT_PLUGIN_MARKET_VIEW_STATE.searchQuery,
    pluginTypeFilter,
    marketplaceSortBy,
    showInstalledPlugins: typeof parsed.showInstalledPlugins === 'boolean'
      ? parsed.showInstalledPlugins
      : DEFAULT_PLUGIN_MARKET_VIEW_STATE.showInstalledPlugins,
  }
}

// 插件市场页：只展示市场索引、安装状态和版本信息
export function PluginMarketplacePage({ embedded = false }: PluginMarketplacePageProps) {
  return (
    <RestartProvider>
      <PluginMarketplacePageContent embedded={embedded} />
    </RestartProvider>
  )
}

// 内部组件：实际内容
function PluginMarketplacePageContent({ embedded }: Required<PluginMarketplacePageProps>) {
  const navigate = useNavigate()
  const scrollViewportRef = useRef<HTMLDivElement | null>(null)
  const scrollRestoredRef = useRef(false)
  // initialViewState 用 useState lazy init 而非 useRef——避免渲染期 ref.current 访问（React 19 refs 规则）
  const [initialViewState] = useState(readPluginMarketplaceViewState)
  const settingsRoute: '/plugin-mirrors' | '/plugin-mirrors/embed' = embedded
    ? '/plugin-mirrors/embed'
    : '/plugin-mirrors'
  const [restartNoticeVisible, setRestartNoticeVisible] = useState(
    () => localStorage.getItem('plugins-restart-notice-dismissed') !== 'true'
  )
  const [searchQuery, setSearchQuery] = useState(initialViewState.searchQuery)
  const [pluginTypeFilter, setPluginTypeFilter] = useState(initialViewState.pluginTypeFilter)
  const [marketplaceSortBy, setMarketplaceSortBy] = useState<MarketplaceSortKey>(
    initialViewState.marketplaceSortBy
  )
  const [showCompatibleOnly] = useState(
    () => localStorage.getItem(PLUGIN_MARKET_COMPATIBLE_ONLY_KEY) !== 'false'
  )
  const [showInstalledPlugins, setShowInstalledPlugins] = useState(initialViewState.showInstalledPlugins)

  // 安装对话框状态
  const [installDialogOpen, setInstallDialogOpen] = useState(false)
  const [installingPlugin, setInstallingPlugin] = useState<PluginInfo | null>(null)
  const [detailPluginId, setDetailPluginId] = useState<string | null>(null)

  // 数据层：5 个 useQuery + 4 个 useMutation + ws 进度订阅 + 视图逻辑（见 hooks/use-marketplace-data.ts）
  const {
    plugins,
    loading,
    error,
    marketError,
    gitStatus,
    maimaiVersion,
    pluginStats,
    loadProgress,
    likingPluginIds,
    installMutation,
    uninstallMutation,
    updateMutation,
    likeMutation,
    checkPluginCompatibility,
    needsUpdate,
    getStatusBadge,
    getIncompatibleReason,
  } = useMarketplaceData()

  const isFetchingMarketplace = loadProgress?.stage === 'loading' && loadProgress.operation === 'fetch'

  const dismissRestartNotice = () => {
    localStorage.setItem('plugins-restart-notice-dismissed', 'true')
    setRestartNoticeVisible(false)
  }

  // Git 未安装提示（加载到 gitStatus 后提示一次——与旧版编排内行为一致）
  useEffect(() => {
    if (gitStatus && !gitStatus.installed) {
      toast.error('Git 未安装', {
        description: gitStatus.error || '请先安装 Git 才能使用插件安装功能',
      })
    }
  }, [gitStatus])

  // 市场清单加载失败 toast（错误卡已呈现；toast 保持旧版行为）
  useEffect(() => {
    if (marketError) {
      toast.error('加载失败', {
        description: marketError instanceof Error ? marketError.message : '加载失败',
      })
    }
  }, [marketError])

  useEffect(() => {
    sessionStorage.setItem(
      PLUGIN_MARKET_VIEW_STATE_KEY,
      JSON.stringify({
        searchQuery,
        pluginTypeFilter,
        marketplaceSortBy,
        showInstalledPlugins,
      } satisfies PluginMarketplaceViewState)
    )
  }, [marketplaceSortBy, pluginTypeFilter, searchQuery, showInstalledPlugins])

  useEffect(() => {
    const viewport = scrollViewportRef.current
    if (!viewport) {
      return
    }

    const handleScroll = () => {
      sessionStorage.setItem(PLUGIN_MARKET_SCROLL_TOP_KEY, String(viewport.scrollTop))
    }

    viewport.addEventListener('scroll', handleScroll, { passive: true })
    return () => {
      viewport.removeEventListener('scroll', handleScroll)
    }
  }, [])

  useEffect(() => {
    if (scrollRestoredRef.current || loading) {
      return
    }

    const viewport = scrollViewportRef.current
    if (!viewport) {
      return
    }

    const savedScrollTop = Number(sessionStorage.getItem(PLUGIN_MARKET_SCROLL_TOP_KEY) ?? 0)
    if (!Number.isFinite(savedScrollTop) || savedScrollTop <= 0) {
      scrollRestoredRef.current = true
      return
    }

    const frameId = requestAnimationFrame(() => {
      viewport.scrollTop = savedScrollTop
      scrollRestoredRef.current = true
    })

    return () => {
      cancelAnimationFrame(frameId)
    }
  }, [loading, plugins.length])

  // 打开安装对话框
  const openInstallDialog = (plugin: PluginInfo) => {
    if (!gitStatus?.installed) {
      toast.error('无法安装', {
        description: 'Git 未安装',
      })
      return
    }

    // 检查插件兼容性
    if (maimaiVersion && !checkPluginCompatibility(plugin)) {
      toast.error('无法安装', {
        description: getIncompatibleReason(plugin) ?? '插件与当前麦麦版本不兼容',
      })
      return
    }

    setInstallingPlugin(plugin)
    setInstallDialogOpen(true)
  }

  const handleInstallDialogOpenChange = (open: boolean) => {
    if (!open && loadProgress?.operation === 'install' && loadProgress.stage === 'loading') {
      return
    }

    setInstallDialogOpen(open)
    if (!open) {
      setInstallingPlugin(null)
    }
  }

  // 安装插件（数据层 mutation，见 use-marketplace-data.ts）
  const handleInstall = (branch: string) => {
    if (!installingPlugin) return

    if (!branch || branch.trim() === '') {
      toast.error('分支名称不能为空')
      return
    }

    installMutation.mutate({ plugin: installingPlugin, branch })
  }

  // 卸载插件
  const handleUninstall = (plugin: PluginInfo) => {
    uninstallMutation.mutate({ plugin })
  }

  // 更新插件
  const handleUpdate = (plugin: PluginInfo) => {
    if (!gitStatus?.installed) {
      toast.error('无法更新', {
        description: 'Git 未安装',
      })
      return
    }

    // 不兼容的插件不允许更新
    if (maimaiVersion && !checkPluginCompatibility(plugin)) {
      toast.error('无法更新', {
        description: getIncompatibleReason(plugin) ?? '插件与当前麦麦版本不兼容',
      })
      return
    }

    updateMutation.mutate({ plugin })
  }

  // 点赞（likingPluginIds 并发保护保留在视图层，mutation 内 also 维护）
  const handleLike = (plugin: PluginInfo) => {
    const pluginId = plugin.manifest?.id || plugin.id
    if (likingPluginIds.has(pluginId)) {
      return
    }

    likeMutation.mutate({ plugin })
  }

  // 过滤插件用于标签页统计——统一走 use-plugin-filter 纯函数（R4 债清理 P2）
  const getFilteredPluginCount = () => countFilteredPlugins(plugins, {
    searchQuery,
    pluginTypeFilter,
    showCompatibleOnly,
    hideInstalledPlugins: !showInstalledPlugins,
    maimaiVersion,
    checkPluginCompatibility,
  })

  return (
    <ScrollArea className="h-full" viewportRef={scrollViewportRef}>
      <div className="space-y-6 p-4 sm:p-6">
        {/* 标题 */}
        <div
          data-plugin-market-header="true"
          className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4"
        >
          <div>
            <h1 data-plugin-market-title="true" className="text-2xl sm:text-3xl font-bold">
              插件市场
            </h1>
          </div>
        </div>

        {/* 安装提示 */}
        {restartNoticeVisible && (
          // blue 语义色板（重启提示——色板豁免）
          <Card className="border-blue-200 bg-blue-50 dark:bg-blue-950/20 dark:border-blue-900">
            <CardContent className="py-3!">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2">
                  <Info className="h-4 w-4 text-blue-600 flex-shrink-0" />
                  <p className="text-sm text-blue-800 dark:text-blue-200">
                    安装、卸载或更新插件后，部分插件需要<span className="font-semibold">重启麦麦</span>才能生效
                  </p>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={dismissRestartNotice}>
                  我知道了
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Git 状态警告 */}
        {gitStatus && !gitStatus.installed && (
          // orange 语义色板（Git 未安装警告——色板豁免）
          <Card className="border-orange-600 bg-orange-50 dark:bg-orange-950/20">
            <CardHeader>
              <div className="flex items-center gap-3">
                <AlertTriangle className="h-5 w-5 text-orange-600" />
                <div>
                  <CardTitle className="text-lg text-orange-900 dark:text-orange-100">
                    Git 未安装
                  </CardTitle>
                  <CardDescription className="text-orange-800 dark:text-orange-200">
                    {gitStatus.error || '请先安装 Git 才能使用插件安装功能'}
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-orange-800 dark:text-orange-200">
                您可以从 <a href="https://git-scm.com/downloads" target="_blank" rel="noopener noreferrer" className="underline font-medium">git-scm.com</a> 下载并安装 Git。
                安装完成后，请重启麦麦应用。
              </p>
            </CardContent>
          </Card>
        )}

        {/* 搜索和筛选栏 */}
        <Card className="p-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            {/* 搜索框 */}
            <div className="relative w-full sm:max-w-md sm:flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="搜索插件..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>

            {/* 类型筛选 */}
            <Select value={pluginTypeFilter} onValueChange={setPluginTypeFilter}>
              <SelectTrigger
                aria-label="类型筛选"
                title="类型筛选"
                className="w-full justify-center gap-1 px-2 sm:w-12"
              >
                <Filter className="h-4 w-4" />
                <span className="sr-only">
                  <SelectValue placeholder="选择类型" />
                </span>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部类型</SelectItem>
                {PLUGIN_TYPE_OPTIONS.map(option => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* 排序 */}
            <Select
              value={marketplaceSortBy}
              onValueChange={(value) => setMarketplaceSortBy(value as MarketplaceSortKey)}
            >
              <SelectTrigger
                aria-label="排序"
                title="排序"
                className="w-full justify-center gap-1 px-2 sm:w-12"
              >
                <ArrowUpDown className="h-4 w-4" />
                <span className="sr-only">
                  <SelectValue placeholder="排序" />
                </span>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="default">推荐排序</SelectItem>
                <SelectItem value="latest">最新上架</SelectItem>
                <SelectItem value="downloads">下载最多</SelectItem>
                <SelectItem value="likes">点赞最多</SelectItem>
                <SelectItem value="rating">评分最高</SelectItem>
              </SelectContent>
            </Select>

            <Badge
              variant="outline"
              data-plugin-market-count-badge="true"
              className="h-9 border-input bg-transparent px-3 text-sm font-normal"
            >
              全部插件 {getFilteredPluginCount()}
            </Badge>

            <Button
              type="button"
              variant="ghost"
              data-plugin-market-settings-button="true"
              className="w-full bg-transparent shadow-none hover:bg-transparent sm:ml-auto sm:w-auto"
              // TanStack Router 类型推断未含 protectedRoute 下路由（mingtang 已知问题，同 use-auth.ts）
              onClick={() => navigate({ to: settingsRoute as never })}
            >
              <Settings2 className="h-4 w-4 mr-2" />
              设置
            </Button>

            {/* 兼容性筛选 */}
            <div className="flex w-full items-center justify-between gap-3 sm:w-auto sm:min-w-fit sm:flex-col sm:items-center sm:justify-center sm:gap-1">
              <label
                htmlFor="show-installed-plugins"
                className="cursor-pointer text-xs font-medium leading-none text-muted-foreground whitespace-nowrap"
              >
                显示已安装
              </label>
              <Switch
                id="show-installed-plugins"
                checked={showInstalledPlugins}
                onCheckedChange={setShowInstalledPlugins}
              />
            </div>
          </div>
          {isFetchingMarketplace && (
            <div
              className="mt-3 flex min-w-0 items-center gap-2 rounded-md border bg-background/85 px-3 py-2 text-xs shadow-sm backdrop-blur"
              aria-live="polite"
            >
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
              <span className="shrink-0 font-medium">加载插件市场</span>
              <span className="min-w-0 truncate text-muted-foreground">
                {loadProgress.message || '正在获取插件清单'}
              </span>
            </div>
          )}
        </Card>

        {/* 加载错误显示 */}
        {loadProgress
          && loadProgress.operation === 'fetch'
          && loadProgress.stage === 'error'
          && loadProgress.error && (
          <Card className="border-destructive bg-destructive/10">
            <CardHeader>
              <div className="flex items-center gap-3">
                <AlertTriangle className="h-5 w-5 text-destructive" />
                <div>
                  <CardTitle className="text-lg text-destructive">
                    加载失败
                  </CardTitle>
                  <CardDescription className="text-destructive/80">
                    {loadProgress.error}
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
          </Card>
        )}

        {/* 插件卡片网格 */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <ThinkingIllustration size="lg" />
          </div>
        ) : error ? (
          <Card className="p-6">
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
              <h3 className="text-lg font-semibold mb-2">加载失败</h3>
              <p className="text-sm text-muted-foreground mb-4">{error}</p>
              <Button onClick={() => window.location.reload()}>
                重新加载
              </Button>
            </div>
          </Card>
        ) : (
          <MarketplaceTab
            plugins={plugins}
            searchQuery={searchQuery}
            pluginTypeFilter={pluginTypeFilter}
            showCompatibleOnly={showCompatibleOnly}
            hideInstalledPlugins={!showInstalledPlugins}
            sortBy={marketplaceSortBy}
            gitStatus={gitStatus}
            maimaiVersion={maimaiVersion}
            pluginStats={pluginStats}
            loadProgress={loadProgress}
            likingPluginIds={likingPluginIds}
            onInstall={openInstallDialog}
            onLike={handleLike}
            onUpdate={handleUpdate}
            onUninstall={handleUninstall}
            onDetail={(plugin) => setDetailPluginId(plugin.id)}
            checkPluginCompatibility={checkPluginCompatibility}
            needsUpdate={needsUpdate}
            getStatusBadge={getStatusBadge}
            getIncompatibleReason={getIncompatibleReason}
          />
        )}

        {/* 安装对话框 */}
        <InstallDialog
          open={installDialogOpen}
          plugin={installingPlugin}
          loadProgress={loadProgress}
          onOpenChange={handleInstallDialogOpenChange}
          onInstall={handleInstall}
        />

        <Dialog open={detailPluginId !== null} onOpenChange={(open) => !open && setDetailPluginId(null)}>
          <DialogContent className="max-w-[calc(100vw-2rem)] p-0 [--dialog-width:88rem]" hideCloseButton>
            {detailPluginId ? (
              <PluginDetailPage
                embedded={embedded}
                mode="dialog"
                onClose={() => setDetailPluginId(null)}
                pluginId={detailPluginId}
              />
            ) : null}
          </DialogContent>
        </Dialog>

        {/* 重启遮罩层 */}
        <RestartOverlay />
      </div>
    </ScrollArea>
  )
}
