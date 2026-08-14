/**
 * plugin-config 主页面（导出入口）——插件列表页壳 + PluginConfigPageContent。
 *
 * R4 债清理 P1 纯文件级拆分：PluginDetailsPanel → ./details-panel；
 * PluginConfigEditor → ./editor；本文件只保留导出入口与列表页内容。
 */
import { useContext, useState } from 'react'

import { ScrollArea } from '@/components/ui/scroll-area'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { RestartOverlay } from '@/components/restart-overlay'
import { RestartProvider, useRestart } from '@/lib/restart-context'
import { ThemeProviderContext } from '@/lib/theme-context'
import type { InstalledPlugin } from '@/lib/plugin-api'
import { PluginIcon } from '@/features/plugin/shared/plugin-icon'
import { getPluginTypeLabel } from '@/features/plugin/shared/types'
import {
  AlertCircle,
  AlertTriangle,
  ArrowUp,
  ChevronRight,
  Loader2,
  Package,
  RefreshCw,
  RotateCw,
  Search,
  Settings,
  Trash2,
} from 'lucide-react'

import { DeletePluginDialog, LoadFailureDetailDialog, UpdatePluginDialog } from './dialogs'
import { PluginConfigEditor } from './editor'
import { usePluginLifecycle } from './hooks/use-plugin-lifecycle'
import { usePluginList } from './hooks/use-plugin-list'

// ---- PluginConfigPage（导出入口） ----

export function PluginConfigPage() {
  return (
    <RestartProvider>
      <PluginConfigPageContent />
    </RestartProvider>
  )
}

// 内部组件：实际内容
function PluginConfigPageContent() {
  const { themeConfig } = useContext(ThemeProviderContext)
  const { triggerRestart, isRestarting } = useRestart()

  const {
    plugins,
    loading,
    selectedPlugin,
    selectedPluginTab,
    openPluginConfig,
    closePluginConfig,
    loadPlugins,
    searchQuery,
    setSearchQuery,
    showUpdateOnly,
    setShowUpdateOnly,
    visiblePlugins,
    actingPluginId,
    setActingPluginId,
    performTogglePlugin,
    checkingUpdates,
    getPluginUpdateState,
    getPluginRepositoryUrl,
    isPluginDisabled,
    isPluginLoadFailed,
    getPluginStatusBarClassName,
    getPluginStatusLabel,
    getPluginStatusMeta,
    installedCount,
    disabledCount,
    loadingCount,
    circuitOpenCount,
    loadFailedCount,
    enabledCount,
    loadSuccessCount,
    loadSuccessPercent,
    loadFailedPercent,
    loadingPercent,
    circuitPercent,
    showsCircuitSummary,
    modernLoadSummaryLabel,
    futureRetroPluginSummaryLabel,
  } = usePluginList()

  const {
    deleteDialogOpen,
    setDeleteDialogOpen,
    deletingPlugin,
    deleteProgress,
    openDeletePluginDialog,
    closeDeletePluginDialog,
    handleConfirmDeletePlugin,
    updateDialogOpen,
    setUpdateDialogOpen,
    updatingPlugin,
    updateProgress,
    openUpdatePluginDialog,
    closeUpdatePluginDialog,
    handleConfirmUpdatePlugin,
  } = usePluginLifecycle({
    getPluginRepositoryUrl,
    onChanged: loadPlugins,
    setActingPluginId,
  })

  const isModernDashboardStyle = themeConfig.dashboardStyle === 'modern'
  const isFutureRetroDashboardStyle = themeConfig.dashboardStyle === 'future-retro'
  const [loadFailureDetailPlugin, setLoadFailureDetailPlugin] = useState<InstalledPlugin | null>(null)

  // 如果选中了插件，显示配置编辑器
  if (selectedPlugin) {
    return (
      <>
        <ScrollArea className="h-full">
          <div className="px-5 pt-0 pb-4 sm:px-7 sm:pb-6 lg:px-8">
            <PluginConfigEditor
              plugin={selectedPlugin}
              initialTab={selectedPluginTab}
              onBack={closePluginConfig}
            />
          </div>
        </ScrollArea>
        <RestartOverlay />
      </>
    )
  }

  return (
    <>
      <ScrollArea className="h-full">
      <div className="space-y-4 p-4 sm:space-y-6 sm:p-6">
        <div className="flex flex-nowrap items-center gap-2 sm:gap-3">
          <div className="relative min-w-0 flex-1 basis-0 sm:basis-72">
            <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
            <Input
              placeholder="搜索插件..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <div
            data-dashboard-input="true"
            className="border-input flex h-9 shrink-0 items-center gap-1.5 rounded-md border bg-transparent px-2 py-1 text-sm font-medium whitespace-nowrap shadow-sm transition-colors sm:gap-2 sm:px-3"
          >
            <Label htmlFor="show-update-only" className="cursor-pointer text-sm font-medium">
              有更新
            </Label>
            <Switch
              id="show-update-only"
              checked={showUpdateOnly}
              disabled={checkingUpdates}
              onCheckedChange={setShowUpdateOnly}
            />
          </div>
          <Button
            variant="outline"
            size="icon"
            className="shrink-0"
            onClick={loadPlugins}
            aria-label="刷新"
            title="刷新"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-9 shrink-0 px-2 sm:px-3"
            onClick={() => triggerRestart()}
            disabled={isRestarting}
            title="重启麦麦"
          >
            <RotateCw className={`h-4 w-4 ${isRestarting ? 'animate-spin' : ''} sm:mr-2`} />
            <span className="hidden sm:inline">重启麦麦</span>
          </Button>
        </div>

        {/* 统计信息 */}
        {isModernDashboardStyle ? (
          <Card>
            <CardContent className="space-y-3 p-4!">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                <span className="flex items-center gap-2">
                  <Package className="text-muted-foreground h-4 w-4" />
                  已安装 <strong>{installedCount}</strong> 个插件
                </span>
                <span>
                  已启用 <strong className="text-emerald-600">{enabledCount}</strong> 个 {/* emerald 色板（成功——色板豁免） */}
                </span>
                <span>
                  已禁用 <strong className="text-muted-foreground">{disabledCount}</strong> 个
                </span>
                <span>
                  加载中 <strong className="text-sky-600">{loadingCount}</strong> 个 {/* sky 色板（加载中——色板豁免） */}
                </span>
                {showsCircuitSummary && (
                  <span>
                    熔断中 <strong className="text-orange-600">{circuitOpenCount}</strong> 个 {/* orange 色板（熔断——色板豁免） */}
                  </span>
                )}
              </div>
              <div
                className="flex items-center gap-3 border-t pt-3 text-sm"
                aria-label={modernLoadSummaryLabel}
              >
                <span className="sr-only">{modernLoadSummaryLabel}</span>
                <strong className="w-8 text-right text-emerald-600">{loadSuccessCount}</strong> {/* emerald 色板（成功——色板豁免） */}
                <div
                  className="bg-muted flex h-3 min-w-28 flex-1 overflow-hidden"
                  aria-hidden="true"
                >
                  <div className="bg-emerald-500" style={{ width: `${loadSuccessPercent}%` }} /> {/* emerald 色板（成功——色板豁免） */}
                  <div className="bg-sky-500" style={{ width: `${loadingPercent}%` }} /> {/* sky 色板（加载中——色板豁免） */}
                  <div className="bg-orange-500" style={{ width: `${circuitPercent}%` }} /> {/* orange 色板（熔断——色板豁免） */}
                  <div className="bg-red-500" style={{ width: `${loadFailedPercent}%` }} /> {/* red 色板（失败——色板豁免） */}
                </div>
                <strong className="w-8 text-right text-red-600">{loadFailedCount}</strong> {/* red 色板（失败——色板豁免） */}
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            <div className="space-y-2" aria-label={futureRetroPluginSummaryLabel}>
              <span className="sr-only">{futureRetroPluginSummaryLabel}</span>
              <div className="bg-muted flex h-3 w-full overflow-hidden" aria-hidden="true">
                {plugins.length > 0 ? (
                  plugins.map((plugin, index) => (
                    <div
                      key={`${plugin.id}-${index}`}
                      className={`min-w-0 flex-1 ${getPluginStatusBarClassName(plugin)} ${
                        index < plugins.length - 1 ? 'border-background border-r' : ''
                      }`}
                      title={`${plugin.manifest.name}：${getPluginStatusLabel(plugin)}`}
                    />
                  ))
                ) : (
                  <div className="bg-muted-foreground/20 h-full flex-1" />
                )}
              </div>
              <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                <span className="flex items-center gap-1.5">
                  插件 <strong className="text-foreground">{installedCount}</strong>个
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" /> {/* emerald 色板（成功——色板豁免） */}
                  启用 <strong className="text-emerald-600">{enabledCount}</strong> 个 {/* emerald 色板（成功——色板豁免） */}
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="bg-muted-foreground/45 h-2 w-2 rounded-full" />
                  禁用 <strong className="text-muted-foreground">{disabledCount}</strong> 个
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-sky-500" /> {/* sky 色板（加载中——色板豁免） */}
                  加载中 <strong className="text-sky-600">{loadingCount}</strong> 个 {/* sky 色板（加载中——色板豁免） */}
                </span>
                {showsCircuitSummary && (
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-orange-500" /> {/* orange 色板（熔断——色板豁免） */}
                    熔断中 <strong className="text-orange-600">{circuitOpenCount}</strong> 个 {/* orange 色板（熔断——色板豁免） */}
                  </span>
                )}
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-red-500" /> {/* red 色板（失败——色板豁免） */}
                  启动失败 <strong className="text-red-600">{loadFailedCount}</strong> 个 {/* red 色板（失败——色板豁免） */}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* 插件列表 */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="text-muted-foreground h-8 w-8 animate-spin" />
          </div>
        ) : visiblePlugins.length === 0 ? (
          <div className="flex flex-col items-center justify-center space-y-4 py-12">
            <Package className="text-muted-foreground/50 h-16 w-16" />
            <div className="space-y-2 text-center">
              <p className="text-muted-foreground text-lg font-medium">
                {showUpdateOnly
                  ? '暂无可更新插件'
                  : searchQuery
                    ? '没有找到匹配的插件'
                    : '暂无已安装的插件'}
              </p>
              <p className="text-muted-foreground text-sm">
                {showUpdateOnly
                  ? '当前已安装插件没有发现新版本'
                  : searchQuery
                    ? '尝试其他搜索关键词'
                    : '前往插件市场安装插件'}
              </p>
            </div>
          </div>
        ) : (
          <div className="divide-border/80 divide-y">
            {visiblePlugins.map((plugin) => {
              const statusMeta = getPluginStatusMeta(plugin)
              const pluginActing = actingPluginId === plugin.id
              const pluginDisabled = isPluginDisabled(plugin)
              const updateState = getPluginUpdateState(plugin)
              const pluginLoadFailed = isPluginLoadFailed(plugin)
              const loadFailureReason = plugin.load_error?.trim() || '运行时未返回具体失败原因'
              return (
                <div
                  key={plugin.id}
                  data-plugin-list-item="true"
                  className={`hover:bg-muted/55 focus-visible:bg-muted/55 relative flex cursor-pointer flex-col justify-between gap-2 py-2.5 transition-all duration-150 ease-out hover:-translate-y-0.5 hover:shadow-md focus-visible:-translate-y-0.5 focus-visible:shadow-md focus-visible:outline-none sm:min-h-0 sm:flex-row sm:items-center sm:gap-3 sm:px-2 sm:py-3 ${
                    isPluginDisabled(plugin) ? 'opacity-70' : ''
                  }`}
                  role="button"
                  tabIndex={0}
                  onClick={() => openPluginConfig(plugin)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      openPluginConfig(plugin)
                    }
                  }}
                >
                  <div className="flex min-w-0 items-start gap-3 sm:items-center">
                    <span
                      className={`mt-4 flex-shrink-0 sm:mt-0 ${
                        isFutureRetroDashboardStyle ? 'h-12 w-2' : 'h-2.5 w-2.5 rounded-full'
                      } ${statusMeta.dotClassName}`}
                      title={statusMeta.label}
                      aria-label={statusMeta.label}
                    />
                    <div className="flex w-12 flex-shrink-0 flex-col items-center gap-1 sm:w-10">
                      <PluginIcon
                        pluginId={plugin.id}
                        manifest={plugin.manifest}
                        installed
                        className="h-12 w-12 sm:h-10 sm:w-10"
                      />
                      <span className="text-muted-foreground text-[0.65rem] leading-none">
                        v{plugin.manifest.version}
                      </span>
                    </div>
                    <div className="min-w-0 flex-1 space-y-2 sm:space-y-1">
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <h3 className="min-w-0 text-sm leading-snug font-medium break-words sm:truncate sm:text-base">
                          {plugin.manifest.name}
                        </h3>
                        <Badge variant="outline" className="flex-shrink-0 text-xs">
                          {getPluginTypeLabel(plugin)}
                        </Badge>
                        {statusMeta.showsBadge !== false && (
                          <Badge
                            variant="outline"
                            className={`flex-shrink-0 gap-1 text-xs ${statusMeta.badgeClassName ?? ''}`}
                          >
                            {statusMeta.icon === 'loading' && (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            )}
                            {statusMeta.icon === 'warning' && <AlertCircle className="h-3 w-3" />}
                            {statusMeta.icon === 'circuit' && <AlertTriangle className="h-3 w-3" />}
                            {statusMeta.label}
                          </Badge>
                        )}
                      </div>
                      <p className="text-muted-foreground line-clamp-2 text-sm leading-relaxed sm:truncate sm:leading-normal">
                        {plugin.manifest.description || '暂无描述'}
                      </p>
                      {pluginLoadFailed && (
                        <div className="flex min-w-0 flex-col gap-2 rounded-md border border-red-200 bg-red-50/80 px-3 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/25 dark:text-red-300 sm:flex-row sm:items-center"> {/* red 色板（失败——色板豁免） */}
                          <div className="flex min-w-0 flex-1 items-start gap-1.5">
                            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                            <span className="min-w-0 line-clamp-2 break-words">
                              失败原因：{loadFailureReason}
                            </span>
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7 shrink-0 border-red-300 px-2 text-xs text-red-700 hover:bg-red-100 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950" /* red 色板（失败——色板豁免） */
                            onClick={(event) => {
                              event.stopPropagation()
                              setLoadFailureDetailPlugin(plugin)
                            }}
                          >
                            查看详情
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center justify-end gap-2 border-t pt-2 sm:flex-shrink-0 sm:border-t-0 sm:pt-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-9 w-9 p-0"
                      title="配置"
                      aria-label="配置"
                      onClick={() => openPluginConfig(plugin)}
                    >
                      <Settings className="h-4 w-4" />
                    </Button>
                    <div
                      className="flex h-9 w-9 items-center justify-center"
                      title={pluginDisabled ? '启动插件' : '关闭插件'}
                    >
                      {pluginActing && <Loader2 className="h-4 w-4 animate-spin" />}
                      <Switch
                        data-plugin-list-switch="true"
                        checked={!pluginDisabled}
                        disabled={pluginActing}
                        aria-label={pluginDisabled ? '启动插件' : '关闭插件'}
                        onClick={(event) => event.stopPropagation()}
                        onCheckedChange={() => void performTogglePlugin(plugin)}
                      />
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="relative h-9 w-9 p-0"
                      disabled={pluginActing || !updateState.canUpdate}
                      title={updateState.title}
                      aria-label={updateState.title || '更新/升级'}
                      onClick={(event) => openUpdatePluginDialog(plugin, event)}
                    >
                      {updateState.hasUpdate && (
                        <span
                          className="ring-background absolute -top-1 -right-1 h-3 w-3 rounded-sm bg-yellow-400 ring-2" /* yellow 色板（更新提示——色板豁免） */
                          aria-hidden="true"
                        />
                      )}
                      {pluginActing ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : checkingUpdates ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <ArrowUp className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      className="h-9 w-9 p-0"
                      disabled={pluginActing}
                      title="删除"
                      aria-label="删除"
                      onClick={(event) => openDeletePluginDialog(plugin, event)}
                    >
                      {pluginActing ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                    <ChevronRight className="text-muted-foreground h-4 w-4" />
                  </div>
                </div>
              )
            })}
          </div>
        )}

        <LoadFailureDetailDialog
          plugin={loadFailureDetailPlugin}
          onOpenChange={(open) => {
            if (!open) {
              setLoadFailureDetailPlugin(null)
            }
          }}
          getPluginStatusLabel={getPluginStatusLabel}
        />

        <UpdatePluginDialog
          open={updateDialogOpen}
          onOpenChange={setUpdateDialogOpen}
          updatingPlugin={updatingPlugin}
          updateProgress={updateProgress}
          onClose={closeUpdatePluginDialog}
          onConfirm={handleConfirmUpdatePlugin}
        />

        <DeletePluginDialog
          open={deleteDialogOpen}
          onOpenChange={setDeleteDialogOpen}
          deletingPlugin={deletingPlugin}
          deleteProgress={deleteProgress}
          onClose={closeDeletePluginDialog}
          onConfirm={handleConfirmDeletePlugin}
        />
      </div>
      </ScrollArea>
      <RestartOverlay />
    </>
  )
}
