import { Download, Loader2, RefreshCw, ThumbsUp, Trash2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { PluginProgressBox } from '@/features/plugin/components/plugin-progress-box'
import { PluginIcon } from '@/features/plugin/shared/plugin-icon'
import type { GitStatus, MaimaiVersion, PluginInfo, PluginLoadProgress, PluginStatsData } from '@/features/plugin/shared/types'
import { getPluginTypeLabel } from '@/features/plugin/shared/types'

// PluginCardProps —— 卡片接口单一来源（R4 债清理 P2：MarketplaceTabProps 经 ts Pick 派生，避免 16-prop 重复声明）
export interface PluginCardProps {
  plugin: PluginInfo
  gitStatus: GitStatus | null
  maimaiVersion: MaimaiVersion | null
  pluginStats: Record<string, PluginStatsData>
  loadProgress: PluginLoadProgress | null
  likingPluginIds: Set<string>
  onInstall: (plugin: PluginInfo) => void
  onLike: (plugin: PluginInfo) => void
  onUpdate: (plugin: PluginInfo) => void
  onUninstall: (plugin: PluginInfo) => void
  onDetail: (plugin: PluginInfo) => void
  checkPluginCompatibility: (plugin: PluginInfo) => boolean
  needsUpdate: (plugin: PluginInfo) => boolean
  getStatusBadge: (plugin: PluginInfo) => React.JSX.Element | null
  getIncompatibleReason: (plugin: PluginInfo) => string | null
}

export function PluginCard({
  plugin,
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
}: PluginCardProps) {
  const stats = [plugin.manifest?.id]
    .map(id => id ? pluginStats[id] : undefined)
    .find(Boolean)
  const likeCount = stats?.likes ?? 0
  const isLiked = stats?.liked === true
  const isLiking = likingPluginIds.has(plugin.manifest?.id || plugin.id)
  const isInstalling = loadProgress?.operation === 'install'
    && loadProgress.stage === 'loading'
    && loadProgress?.plugin_id === plugin.id
  const isAnyPluginInstalling = loadProgress?.operation === 'install' && loadProgress.stage === 'loading'

  return (
    <Card
      key={plugin.id}
      className="flex h-full flex-col transition-shadow hover:shadow-md"
    >
      <CardHeader className="p-4 pb-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-start gap-2.5">
            <PluginIcon
              pluginId={plugin.id}
              manifest={plugin.manifest}
              installed={plugin.installed}
              marketplaceIconUrl={plugin.assets?.icon_64}
              className="h-9 w-9 rounded-md"
              iconClassName="h-4 w-4"
            />
            <CardTitle className="min-w-0 text-base leading-snug">{plugin.manifest?.name || plugin.id}</CardTitle>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <Badge variant="secondary" className="whitespace-nowrap px-1.5 py-0 text-[11px]">
              {getPluginTypeLabel(plugin)}
            </Badge>
            {getStatusBadge(plugin)}
          </div>
        </div>
        <CardDescription className="line-clamp-2 min-h-[2.0625rem] text-xs leading-snug">
          {plugin.manifest?.description || '无描述'}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1 px-4 pb-2.5">
        <div className="space-y-2">
          {/* 统计信息 */}
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <span>下载</span>
              <span>{(stats?.downloads ?? plugin.downloads ?? 0).toLocaleString()}</span>
            </div>
            <div className="flex items-center gap-1">
              <span>评分</span>
              <span>{(stats?.rating ?? plugin.rating ?? 0).toFixed(1)}</span>
            </div>
            <div className="flex items-center gap-1">
              <span>点赞</span>
              <span>{likeCount.toLocaleString()}</span>
            </div>
          </div>
          {/* 标签 */}
          <div className="flex flex-wrap gap-1.5">
            {plugin.manifest?.keywords && plugin.manifest.keywords.slice(0, 3).map((keyword) => (
              <Badge key={keyword} variant="outline" className="px-1.5 py-0 text-[11px]">
                {keyword}
              </Badge>
            ))}
            {plugin.manifest?.keywords && plugin.manifest.keywords.length > 3 && (
              <Badge variant="outline" className="px-1.5 py-0 text-[11px]">
                +{plugin.manifest.keywords.length - 3}
              </Badge>
            )}
          </div>
          {/* 版本和作者 */}
          <div className="space-y-1 border-t pt-2 text-xs text-muted-foreground">
            <div>v{plugin.manifest?.version || 'unknown'} · {plugin.manifest?.author?.name || 'Unknown'}</div>
            {/* 支持版本 */}
            {plugin.manifest?.host_application && (
              <div className="flex items-center gap-1">
                <span>支持:</span>
                <span className="font-medium">
                  {plugin.manifest.host_application.min_version}
                  {plugin.manifest.host_application.max_version 
                    ? ` - ${plugin.manifest.host_application.max_version}`
                    : ' - 最新版本'
                  }
                </span>
              </div>
            )}
          </div>
        </div>
      </CardContent>
      <CardFooter className="mt-auto px-4 pb-4 pt-1.5">
        <div className="grid w-full grid-cols-3 gap-2 sm:flex sm:items-center sm:justify-end">
          <Button
            variant={isLiked ? 'secondary' : 'outline'}
            size="sm"
            className="w-full px-2 sm:w-auto"
            title={isLiked ? '取消点赞' : '点赞'}
            aria-label={isLiked ? '取消点赞' : '点赞'}
            disabled={isLiking}
            onClick={() => onLike(plugin)}
          >
            {isLiking ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ThumbsUp className={isLiked ? 'h-4 w-4 fill-current' : 'h-4 w-4'} />
            )}
            <span>{likeCount.toLocaleString()}</span>
          </Button>
          <Button 
            variant="outline"
            size="sm"
            className="w-full sm:w-auto"
            onClick={() => onDetail(plugin)}
          >
            查看详情
          </Button>
          {plugin.installed ? (
            needsUpdate(plugin) ? (
              <Button 
                size="sm"
                className="w-full sm:w-auto"
                disabled={!gitStatus?.installed || (maimaiVersion !== null && !checkPluginCompatibility(plugin))}
                title={
                  !gitStatus?.installed
                    ? 'Git 未安装'
                    : (maimaiVersion !== null && !checkPluginCompatibility(plugin))
                      ? (getIncompatibleReason(plugin) ?? '插件与当前麦麦版本不兼容')
                      : undefined
                }
                onClick={() => onUpdate(plugin)}
              >
                <RefreshCw className="h-4 w-4 mr-1" />
                更新
              </Button>
            ) : (
              <Button 
                variant="destructive" 
                size="sm"
                className="w-full sm:w-auto"
                disabled={!gitStatus?.installed}
                title={!gitStatus?.installed ? 'Git 未安装' : undefined}
                onClick={() => onUninstall(plugin)}
              >
                <Trash2 className="h-4 w-4 mr-1" />
                卸载
              </Button>
            )
          ) : (
            <Button 
              size="sm"
              className="w-full px-0 sm:w-8"
              disabled={
                !gitStatus?.installed || 
                isAnyPluginInstalling ||
                (maimaiVersion !== null && !checkPluginCompatibility(plugin))
              }
              title={
                !gitStatus?.installed 
                  ? 'Git 未安装' 
                  : (maimaiVersion !== null && !checkPluginCompatibility(plugin))
                    ? (getIncompatibleReason(plugin) ?? '插件与当前麦麦版本不兼容')
                    : undefined
              }
              aria-label={isInstalling ? '正在安装' : '安装'}
              onClick={() => onInstall(plugin)}
            >
              {isInstalling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            </Button>
          )}
        </div>
      </CardFooter>
      {/* 安装/卸载/更新进度显示 - 在卡片下方（PluginProgressBox 公共组件） */}
      {loadProgress && 
        (loadProgress.stage === 'loading' || loadProgress.stage === 'success' || loadProgress.stage === 'error') && 
        loadProgress.operation !== 'fetch' && 
        loadProgress.plugin_id === plugin.id && (
        <div className="-mt-1 px-4 pb-4">
          <PluginProgressBox
            progress={loadProgress}
            actionLabel={loadProgress.operation === 'install'
              ? '安装'
              : loadProgress.operation === 'uninstall'
                ? '卸载'
                : '更新'}
            compact
          />
        </div>
      )}
    </Card>
  )
}