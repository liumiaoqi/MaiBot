import {
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  Database,
  Eye,
  Folder,
  FolderOpen,
  HardDrive,
  Image,
  ImageOff,
  Loader2,
  RefreshCw,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/hooks/use-toast'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import {
  cleanupLocalCache,
  deleteLocalCacheImagesByDateRange,
  deleteLocalCacheImagesOlderThanRecentDays,
  deleteLocalCacheLogDirectory,
  deleteLocalCacheImage,
  getLocalCacheImagePreviewUrl,
  getLocalCacheImages,
  getLocalCacheLogDirectories,
  getLocalCacheStats,
  type CacheDirectoryStats,
  type DatabaseTableStats,
  type LocalCacheImageItem,
  type LocalCacheImageListResponse,
  type LocalCacheImageTarget,
  type LocalCacheLogDirectoryItem,
  type LocalCacheLogDirectoryListResponse,
  type LocalCacheCleanupTarget,
  type LocalCacheStats,
  type LogCleanupTable,
} from '@/lib/system-api'

const IMAGE_PAGE_SIZE = 40

type ImageDateFilters = {
  endDate: string
  startDate: string
}

const LOG_CLEANUP_OPTIONS: Array<{
  table: LogCleanupTable
  label: string
  description: string
}> = [
  { table: 'llm_usage', label: 'llm_usage', description: '记录 LLM 调用统计信息' },
  { table: 'tool_records', label: 'tool_records', description: '记录工具使用记录' },
  { table: 'mai_messages', label: 'mai_messages', description: '清理收到的消息' },
]

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '0 B'
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** unitIndex
  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`
}

function CacheIcon({ cacheKey }: { cacheKey: string }) {
  if (cacheKey === 'images') {
    return <Image className="h-4 w-4 text-primary" />
  }
  if (cacheKey === 'emoji') {
    return <Sparkles className="h-4 w-4 text-primary" />
  }
  return <HardDrive className="h-4 w-4 text-primary" />
}

function getImageTarget(cacheKey: string): LocalCacheImageTarget | null {
  if (cacheKey === 'images' || cacheKey === 'emoji') {
    return cacheKey
  }
  return null
}

function formatModifiedTime(timestamp: number): string {
  if (!Number.isFinite(timestamp) || timestamp <= 0) {
    return '-'
  }
  return new Date(timestamp * 1000).toLocaleString('zh-CN')
}

function CacheImagePreview({
  item,
  target,
}: {
  item: LocalCacheImageItem
  target: LocalCacheImageTarget
}) {
  const previewKey = `${target}:${item.relative_path}`
  const previewUrl = getLocalCacheImagePreviewUrl(target, item.relative_path)
  const [preview, setPreview] = useState<{
    hasError: boolean
    key: string
    objectUrl: string | null
  }>({
    hasError: false,
    key: previewKey,
    objectUrl: null,
  })

  useEffect(() => {
    let cancelled = false
    let createdUrl: string | null = null

    void fetchWithAuth(previewUrl, {
      method: 'GET',
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error('图片预览加载失败')
        }
        return response.blob()
      })
      .then((blob) => {
        if (cancelled) {
          return
        }
        createdUrl = URL.createObjectURL(blob)
        setPreview({ hasError: false, key: previewKey, objectUrl: createdUrl })
      })
      .catch(() => {
        if (!cancelled) {
          setPreview({ hasError: true, key: previewKey, objectUrl: null })
        }
      })

    return () => {
      cancelled = true
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl)
      }
    }
  }, [previewKey, previewUrl])

  if (preview.key === previewKey && preview.hasError) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-muted">
        <ImageOff className="h-7 w-7 text-muted-foreground" />
      </div>
    )
  }

  if (preview.key !== previewKey || !preview.objectUrl) {
    return <Skeleton className="h-full w-full" />
  }

  return (
    <img
      src={preview.objectUrl}
      alt={item.file_name}
      className="h-full w-full object-contain"
    />
  )
}

function CacheImageListPanel({
  cleanupDisabled,
  deletingKey,
  filters,
  isLoading,
  list,
  onDelete,
  onDeleteAll,
  onDeleteDateRange,
  onDeleteOlderThanRecentDays,
  onFilterChange,
  onFilterClear,
  onFilterSubmit,
  onPageChange,
  onRefresh,
  target,
}: {
  cleanupDisabled: boolean
  deletingKey: string | null
  filters: ImageDateFilters
  isLoading: boolean
  list: LocalCacheImageListResponse | null
  onDelete: (target: LocalCacheImageTarget, item: LocalCacheImageItem) => void
  onDeleteAll: (target: LocalCacheImageTarget) => void
  onDeleteDateRange: (target: LocalCacheImageTarget) => void
  onDeleteOlderThanRecentDays: (target: LocalCacheImageTarget, days: 1 | 7 | 30) => void
  onFilterChange: (target: LocalCacheImageTarget, filters: ImageDateFilters) => void
  onFilterClear: (target: LocalCacheImageTarget) => void
  onFilterSubmit: (target: LocalCacheImageTarget, filters?: ImageDateFilters) => void
  onPageChange: (target: LocalCacheImageTarget, page: number) => void
  onRefresh: (target: LocalCacheImageTarget) => void
  target: LocalCacheImageTarget
}) {
  const targetLabel = target === 'images' ? '图片缓存' : '表情包缓存'
  const items = list?.data ?? []
  const dateGroups = list?.date_groups ?? []
  const currentPage = list?.page ?? 1
  const pageSize = list?.page_size ?? IMAGE_PAGE_SIZE
  const total = list?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const hasDateFilter = Boolean(filters.startDate || filters.endDate)

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h4 className="text-sm font-semibold">{targetLabel}列表</h4>
          <p className="mt-1 text-xs text-muted-foreground">
            {hasDateFilter ? '当前日期范围内' : '当前列表'}共 {total} 个文件，占用 {formatBytes(list?.total_size ?? 0)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => onRefresh(target)} disabled={isLoading} className="gap-2">
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            刷新列表
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2" disabled={cleanupDisabled || total === 0}>
                <Trash2 className="h-4 w-4" />
                全部删除
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>确认删除全部{targetLabel}？</AlertDialogTitle>
                <AlertDialogDescription>
                  这会删除当前缓存目录中的所有文件，并移除数据库里的相关记录。操作不可撤销。
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>取消</AlertDialogCancel>
                <AlertDialogAction onClick={() => onDeleteAll(target)}>确认删除</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      <div className="rounded-lg border bg-card p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="grid gap-3 sm:grid-cols-2 lg:min-w-[360px]">
            <label className="space-y-1.5" htmlFor={`${target}-cache-start-date`}>
              <span className="text-xs text-muted-foreground">开始日期</span>
              <Input
                id={`${target}-cache-start-date`}
                type="date"
                value={filters.startDate}
                onChange={(event) => onFilterChange(target, { ...filters, startDate: event.target.value })}
              />
            </label>
            <label className="space-y-1.5" htmlFor={`${target}-cache-end-date`}>
              <span className="text-xs text-muted-foreground">结束日期</span>
              <Input
                id={`${target}-cache-end-date`}
                type="date"
                value={filters.endDate}
                onChange={(event) => onFilterChange(target, { ...filters, endDate: event.target.value })}
              />
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" className="gap-2" onClick={() => onFilterSubmit(target)} disabled={isLoading}>
              <CalendarDays className="h-4 w-4" />
              按日期浏览
            </Button>
            <Button variant="ghost" size="sm" onClick={() => onFilterClear(target)} disabled={isLoading || !hasDateFilter}>
              清空日期
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2" disabled={cleanupDisabled || !hasDateFilter}>
                  <Trash2 className="h-4 w-4" />
                  删除区间
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>确认删除当前日期区间内的{targetLabel}？</AlertDialogTitle>
                  <AlertDialogDescription>
                    这会删除 {filters.startDate || '最早'} 到 {filters.endDate || '最晚'} 之间的缓存文件，并移除对应数据库记录。操作不可撤销。
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>取消</AlertDialogCancel>
                  <AlertDialogAction onClick={() => onDeleteDateRange(target)}>确认删除</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {dateGroups.slice(0, 30).map((group) => (
            <Button
              key={group.date}
              variant={filters.startDate === group.date && filters.endDate === group.date ? 'default' : 'outline'}
              size="sm"
              className="h-auto gap-2 py-1.5"
              onClick={() => {
                const nextFilters = { startDate: group.date, endDate: group.date }
                onFilterChange(target, nextFilters)
                onFilterSubmit(target, nextFilters)
              }}
            >
              <span>{group.date}</span>
              <span className="text-xs opacity-70">{group.file_count} 个 / {formatBytes(group.total_size)}</span>
            </Button>
          ))}
          {dateGroups.length === 0 && (
            <span className="text-sm text-muted-foreground">暂无可按日期浏览的缓存文件</span>
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-2 border-t pt-4">
          {[1, 7, 30].map((days) => (
            <AlertDialog key={days}>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" disabled={cleanupDisabled || total === 0}>
                  删除最近 {days} 天以外
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>确认清理旧{targetLabel}？</AlertDialogTitle>
                  <AlertDialogDescription>
                    这会保留最近 {days} 天内的缓存，删除更早的文件，并移除对应数据库记录。操作不可撤销。
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>取消</AlertDialogCancel>
                  <AlertDialogAction onClick={() => onDeleteOlderThanRecentDays(target, days as 1 | 7 | 30)}>
                    确认删除
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        {isLoading && !list ? (
          Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="flex gap-3 rounded-md border p-3">
              <Skeleton className="h-20 w-20 shrink-0" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-3 w-2/3" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
          ))
        ) : items.length === 0 ? (
          <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
            暂无图片缓存
          </div>
        ) : (
          items.map((item) => {
            const itemKey = `${target}:${item.relative_path}`
            const deleting = deletingKey === itemKey
            return (
              <div key={item.relative_path} className="flex flex-col gap-3 rounded-md border p-3 sm:flex-row sm:items-center">
                <div className="h-20 w-20 shrink-0 overflow-hidden rounded-md border bg-muted">
                  <CacheImagePreview item={item} target={target} />
                </div>

                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="max-w-full truncate text-sm font-medium">{item.file_name}</span>
                    <Badge variant="outline">{item.format.toUpperCase()}</Badge>
                    {item.db_id !== null ? (
                      <Badge variant="secondary">数据库记录</Badge>
                    ) : (
                      <Badge variant="outline">仅文件</Badge>
                    )}
                    {target === 'emoji' && item.is_registered !== null && (
                      <Badge variant={item.is_registered ? 'default' : 'secondary'}>
                        {item.is_registered ? '已注册' : '未注册'}
                      </Badge>
                    )}
                    {item.is_banned && <Badge variant="destructive">已禁用</Badge>}
                  </div>
                  <p className="break-all text-xs text-muted-foreground">{item.relative_path}</p>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span>{formatBytes(item.size)}</span>
                    <span>{formatModifiedTime(item.modified_time)}</span>
                    {item.image_hash && <span className="max-w-full truncate font-mono">hash: {item.image_hash}</span>}
                  </div>
                  {item.description && (
                    <p className="line-clamp-2 text-xs text-muted-foreground">{item.description}</p>
                  )}
                </div>

                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="self-end text-destructive hover:text-destructive sm:self-center"
                      disabled={cleanupDisabled || deleting}
                      title="删除"
                    >
                      {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>确认删除这张图片？</AlertDialogTitle>
                      <AlertDialogDescription className="break-words">
                        将删除 <span className="break-all font-mono">{item.file_name}</span>
                        ，并移除对应数据库记录。操作不可撤销。
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>取消</AlertDialogCancel>
                      <AlertDialogAction onClick={() => onDelete(target, item)}>确认删除</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            )
          })
        )}
      </div>

      {total > 0 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-xs text-muted-foreground">
            显示 {(currentPage - 1) * pageSize + 1} 到 {Math.min(currentPage * pageSize, total)}，共 {total} 个
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(target, Math.max(1, currentPage - 1))}
              disabled={isLoading || currentPage <= 1}
            >
              <ChevronLeft className="h-4 w-4" />
              上一页
            </Button>
            <span className="text-xs text-muted-foreground">
              {currentPage} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(target, Math.min(totalPages, currentPage + 1))}
              disabled={isLoading || currentPage >= totalPages}
            >
              下一页
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function LogDirectoryListPanel({
  cleanupDisabled,
  deletingPath,
  isLoading,
  list,
  onDelete,
  onRefresh,
}: {
  cleanupDisabled: boolean
  deletingPath: string | null
  isLoading: boolean
  list: LocalCacheLogDirectoryListResponse | null
  onDelete: (item: LocalCacheLogDirectoryItem) => void
  onRefresh: () => void
}) {
  const items = list?.data ?? []

  return (
    <div className="rounded-lg border bg-card p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h4 className="text-sm font-semibold">日志文件夹</h4>
          <p className="mt-1 text-xs text-muted-foreground">
            共 {list?.total ?? 0} 个可清理位置，子目录统计包含其下级目录文件。
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={isLoading} className="gap-2">
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          刷新列表
        </Button>
      </div>

      <div className="mt-4 space-y-3">
        {isLoading && !list ? (
          Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="rounded-md border p-3">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="mt-2 h-3 w-2/3" />
              <Skeleton className="mt-2 h-3 w-1/2" />
            </div>
          ))
        ) : items.length === 0 ? (
          <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
            暂无日志文件夹
          </div>
        ) : (
          items.map((item) => {
            const deleting = deletingPath === item.relative_path
            const displayName = item.root_files_only ? item.name : item.relative_path
            return (
              <div
                key={item.root_files_only ? '__root_files__' : item.relative_path}
                className="flex flex-col gap-3 rounded-md border p-3 sm:flex-row sm:items-center"
              >
                <div className="flex min-w-0 flex-1 items-start gap-3" style={{ paddingLeft: `${Math.min(item.depth, 5) * 12}px` }}>
                  <div className="mt-0.5 shrink-0 rounded-md bg-muted p-2">
                    {item.root_files_only ? (
                      <HardDrive className="h-4 w-4 text-primary" />
                    ) : (
                      <Folder className="h-4 w-4 text-primary" />
                    )}
                  </div>
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="max-w-full truncate text-sm font-medium">{displayName}</span>
                      {item.root_files_only && <Badge variant="secondary">根目录</Badge>}
                      {item.file_count === 0 && <Badge variant="outline">空</Badge>}
                    </div>
                    <p className="break-all text-xs text-muted-foreground">{item.full_path}</p>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      <span>{item.file_count} 个文件</span>
                      <span>{formatBytes(item.total_size)}</span>
                      <span>{formatModifiedTime(item.modified_time)}</span>
                    </div>
                  </div>
                </div>

                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="self-end gap-2 text-destructive hover:text-destructive sm:self-center"
                      disabled={cleanupDisabled || deleting || item.file_count === 0}
                    >
                      {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                      清理
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>确认清理{displayName}？</AlertDialogTitle>
                      <AlertDialogDescription>
                        {item.root_files_only
                          ? '这会删除 logs 根目录下的日志文件，不会删除任何子文件夹。'
                          : '这会删除该日志文件夹中的所有文件，并清理其下的空子目录。'}
                        操作不可撤销。
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>取消</AlertDialogCancel>
                      <AlertDialogAction onClick={() => onDelete(item)}>确认清理</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

function DirectoryCard({
  item,
  isBrowserOpen,
  isLogBrowserOpen,
  cleanupDisabled,
  onBrowse,
  onBrowseLogs,
  onCleanup,
}: {
  item: CacheDirectoryStats
  isBrowserOpen: boolean
  isLogBrowserOpen: boolean
  cleanupDisabled: boolean
  onBrowse: (target: LocalCacheImageTarget) => void
  onBrowseLogs: () => void
  onCleanup: (target: 'images' | 'emoji' | 'log_files') => void
}) {
  const imageTarget = getImageTarget(item.key)
  const isLogDirectory = item.key === 'logs'
  const cleanupTarget = item.key === 'images' ? 'images' : item.key === 'emoji' ? 'emoji' : item.key === 'logs' ? 'log_files' : null
  const cleanupDescription = cleanupTarget === 'log_files'
    ? '这会删除 logs 目录中的日志文件。操作不可撤销。'
    : '这会删除对应目录中的文件，并移除数据库里的相关记录。操作不可撤销。'
  const cleanupLabel = cleanupTarget === 'images' || cleanupTarget === 'emoji' ? '全部删除' : '清理'

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-2">
            <CacheIcon cacheKey={item.key} />
            <h4 className="font-semibold">{item.label}</h4>
          </div>
          <p className="break-all text-xs text-muted-foreground">{item.path}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {imageTarget && (
            <Button
              variant={isBrowserOpen ? 'default' : 'outline'}
              size="sm"
              className="gap-2"
              onClick={() => onBrowse(imageTarget)}
            >
              <Eye className="h-4 w-4" />
              {isBrowserOpen ? '收起列表' : '浏览图片'}
            </Button>
          )}
          {isLogDirectory && (
            <Button
              variant={isLogBrowserOpen ? 'default' : 'outline'}
              size="sm"
              className="gap-2"
              onClick={onBrowseLogs}
            >
              <FolderOpen className="h-4 w-4" />
              {isLogBrowserOpen ? '收起文件夹' : '浏览文件夹'}
            </Button>
          )}
          {cleanupTarget && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2" disabled={cleanupDisabled}>
                  <Trash2 className="h-4 w-4" />
                  {cleanupLabel}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>确认{cleanupLabel}{item.label}？</AlertDialogTitle>
                  <AlertDialogDescription>
                    {cleanupDescription}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>取消</AlertDialogCancel>
                  <AlertDialogAction onClick={() => onCleanup(cleanupTarget)}>确认{cleanupLabel}</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <div className="text-xs text-muted-foreground">文件数</div>
          <div className="text-lg font-semibold">{item.file_count}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">占用空间</div>
          <div className="text-lg font-semibold">{formatBytes(item.total_size)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">数据库记录</div>
          <div className="text-lg font-semibold">{item.db_records}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">目录状态</div>
          <div className="text-lg font-semibold">{item.exists ? '存在' : '未创建'}</div>
        </div>
      </div>
    </div>
  )
}

export function LocalCacheTab() {
  const { toast } = useToast()
  const [stats, setStats] = useState<LocalCacheStats | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [cleanupTarget, setCleanupTarget] = useState<LocalCacheCleanupTarget | null>(null)
  const [selectedLogTables, setSelectedLogTables] = useState<LogCleanupTable[]>([])
  const [browserTarget, setBrowserTarget] = useState<LocalCacheImageTarget | null>(null)
  const [isLogBrowserOpen, setIsLogBrowserOpen] = useState(false)
  const [imageLists, setImageLists] = useState<Record<LocalCacheImageTarget, LocalCacheImageListResponse | null>>({
    images: null,
    emoji: null,
  })
  const [imagePages, setImagePages] = useState<Record<LocalCacheImageTarget, number>>({
    images: 1,
    emoji: 1,
  })
  const [imageDateFilters, setImageDateFilters] = useState<Record<LocalCacheImageTarget, ImageDateFilters>>({
    images: { endDate: '', startDate: '' },
    emoji: { endDate: '', startDate: '' },
  })
  const [loadingImageTarget, setLoadingImageTarget] = useState<LocalCacheImageTarget | null>(null)
  const [deletingImageKey, setDeletingImageKey] = useState<string | null>(null)
  const [logDirectories, setLogDirectories] = useState<LocalCacheLogDirectoryListResponse | null>(null)
  const [loadingLogDirectories, setLoadingLogDirectories] = useState(false)
  const [deletingLogPath, setDeletingLogPath] = useState<string | null>(null)

  const tableStats = useMemo(() => {
    const rows = new Map<string, DatabaseTableStats>()
    for (const table of stats?.database.tables ?? []) {
      rows.set(table.name, table)
    }
    return rows
  }, [stats?.database.tables])

  const selectedLogRows = selectedLogTables.reduce((total, table) => total + (tableStats.get(table)?.rows ?? 0), 0)
  const totalDatabaseRows = (stats?.database.tables ?? []).reduce((total, table) => total + table.rows, 0)

  const refreshImageList = useCallback(async (
    target: LocalCacheImageTarget,
    page: number,
    filters: ImageDateFilters = imageDateFilters[target]
  ) => {
    setLoadingImageTarget(target)
    try {
      const result = await getLocalCacheImages({
        target,
        page,
        page_size: IMAGE_PAGE_SIZE,
        start_date: filters.startDate || undefined,
        end_date: filters.endDate || undefined,
      })
      setImageLists((current) => ({ ...current, [target]: result }))
    } catch (error) {
      toast({
        title: '获取图片列表失败',
        description: error instanceof Error ? error.message : '请稍后重试',
        variant: 'destructive',
      })
    } finally {
      setLoadingImageTarget(null)
    }
  }, [imageDateFilters, toast])

  const refreshLogDirectories = useCallback(async () => {
    setLoadingLogDirectories(true)
    try {
      setLogDirectories(await getLocalCacheLogDirectories())
    } catch (error) {
      toast({
        title: '获取日志文件夹失败',
        description: error instanceof Error ? error.message : '请稍后重试',
        variant: 'destructive',
      })
    } finally {
      setLoadingLogDirectories(false)
    }
  }, [toast])

  const refreshStats = useCallback(async () => {
    setIsLoading(true)
    try {
      setStats(await getLocalCacheStats())
    } catch (error) {
      toast({
        title: '获取本地缓存失败',
        description: error instanceof Error ? error.message : '请稍后重试',
        variant: 'destructive',
      })
    } finally {
      setIsLoading(false)
    }
  }, [toast])

  const handleBrowseImages = (target: LocalCacheImageTarget) => {
    setBrowserTarget(target)
    void refreshImageList(target, imagePages[target])
  }

  const handleBrowseLogs = () => {
    const nextOpen = !isLogBrowserOpen
    setIsLogBrowserOpen(nextOpen)
    if (nextOpen) {
      void refreshLogDirectories()
    }
  }

  const handleImagePageChange = (target: LocalCacheImageTarget, page: number) => {
    setImagePages((current) => ({ ...current, [target]: page }))
    void refreshImageList(target, page)
  }

  const handleImageListRefresh = (target: LocalCacheImageTarget) => {
    void refreshImageList(target, imagePages[target])
  }

  const handleImageDateFilterChange = (target: LocalCacheImageTarget, filters: ImageDateFilters) => {
    setImageDateFilters((current) => ({ ...current, [target]: filters }))
  }

  const handleImageDateFilterSubmit = (target: LocalCacheImageTarget, filters = imageDateFilters[target]) => {
    setImagePages((current) => ({ ...current, [target]: 1 }))
    void refreshImageList(target, 1, filters)
  }

  const handleImageDateFilterClear = (target: LocalCacheImageTarget) => {
    const nextFilters = { endDate: '', startDate: '' }
    setImageDateFilters((current) => ({ ...current, [target]: nextFilters }))
    setImagePages((current) => ({ ...current, [target]: 1 }))
    void refreshImageList(target, 1, nextFilters)
  }

  const handleDirectoryCleanup = async (target: 'images' | 'emoji' | 'log_files') => {
    setCleanupTarget(target)
    try {
      const result = await cleanupLocalCache(target)
      await refreshStats()
      if (target === 'images' || target === 'emoji') {
        setImagePages((current) => ({ ...current, [target]: 1 }))
        if (browserTarget === target) {
          await refreshImageList(target, 1)
        }
      }
      if (target === 'log_files' && isLogBrowserOpen) {
        await refreshLogDirectories()
      }
      toast({
        title: result.message,
        description: `删除 ${result.removed_files} 个文件，释放 ${formatBytes(result.removed_bytes)}，移除 ${result.removed_records} 条记录。`,
      })
    } catch (error) {
      toast({
        title: '清理失败',
        description: error instanceof Error ? error.message : '请稍后重试',
        variant: 'destructive',
      })
    } finally {
      setCleanupTarget(null)
    }
  }

  const handleDeleteLogDirectory = async (item: LocalCacheLogDirectoryItem) => {
    setDeletingLogPath(item.relative_path)
    try {
      const result = await deleteLocalCacheLogDirectory(item.relative_path)
      await refreshStats()
      await refreshLogDirectories()
      toast({
        title: result.message,
        description: `删除 ${result.removed_files} 个文件，释放 ${formatBytes(result.removed_bytes)}。`,
      })
    } catch (error) {
      toast({
        title: '清理日志文件夹失败',
        description: error instanceof Error ? error.message : '请稍后重试',
        variant: 'destructive',
      })
    } finally {
      setDeletingLogPath(null)
    }
  }

  const handleDeleteCacheImagesByDateRange = async (target: LocalCacheImageTarget) => {
    const filters = imageDateFilters[target]
    setCleanupTarget(target)
    try {
      const result = await deleteLocalCacheImagesByDateRange(target, filters.startDate, filters.endDate)
      setImagePages((current) => ({ ...current, [target]: 1 }))
      await refreshStats()
      await refreshImageList(target, 1, filters)
      toast({
        title: result.message,
        description: `删除 ${result.removed_files} 个文件，释放 ${formatBytes(result.removed_bytes)}，移除 ${result.removed_records} 条记录。`,
      })
    } catch (error) {
      toast({
        title: '按日期删除失败',
        description: error instanceof Error ? error.message : '请稍后重试',
        variant: 'destructive',
      })
    } finally {
      setCleanupTarget(null)
    }
  }

  const handleDeleteCacheImagesOlderThanRecentDays = async (target: LocalCacheImageTarget, days: 1 | 7 | 30) => {
    setCleanupTarget(target)
    try {
      const result = await deleteLocalCacheImagesOlderThanRecentDays(target, days)
      setImagePages((current) => ({ ...current, [target]: 1 }))
      await refreshStats()
      await refreshImageList(target, 1)
      toast({
        title: result.message,
        description: `删除 ${result.removed_files} 个文件，释放 ${formatBytes(result.removed_bytes)}，移除 ${result.removed_records} 条记录。`,
      })
    } catch (error) {
      toast({
        title: '清理旧缓存失败',
        description: error instanceof Error ? error.message : '请稍后重试',
        variant: 'destructive',
      })
    } finally {
      setCleanupTarget(null)
    }
  }

  const handleDeleteCacheImage = async (target: LocalCacheImageTarget, item: LocalCacheImageItem) => {
    const itemKey = `${target}:${item.relative_path}`
    setDeletingImageKey(itemKey)
    try {
      const result = await deleteLocalCacheImage(target, item.relative_path)
      const remainingTotal = Math.max(0, (imageLists[target]?.total ?? 1) - 1)
      const nextPage = Math.max(1, Math.min(imagePages[target], Math.ceil(remainingTotal / IMAGE_PAGE_SIZE) || 1))

      setImagePages((current) => ({ ...current, [target]: nextPage }))
      await refreshStats()
      await refreshImageList(target, nextPage)
      toast({
        title: result.message,
        description: `删除 ${result.removed_files} 个文件，释放 ${formatBytes(result.removed_bytes)}，移除 ${result.removed_records} 条记录。`,
      })
    } catch (error) {
      toast({
        title: '删除图片失败',
        description: error instanceof Error ? error.message : '请稍后重试',
        variant: 'destructive',
      })
    } finally {
      setDeletingImageKey(null)
    }
  }

  const handleLogCleanup = async () => {
    setCleanupTarget('database_logs')
    try {
      const result = await cleanupLocalCache('database_logs', selectedLogTables)
      setSelectedLogTables([])
      await refreshStats()
      toast({
        title: result.message,
        description: `已清理 ${result.removed_records} 条数据库记录。`,
      })
    } catch (error) {
      toast({
        title: '数据库清理失败',
        description: error instanceof Error ? error.message : '请稍后重试',
        variant: 'destructive',
      })
    } finally {
      setCleanupTarget(null)
    }
  }

  const toggleLogTable = (table: LogCleanupTable, checked: boolean) => {
    setSelectedLogTables((current) => {
      if (checked) {
        return current.includes(table) ? current : [...current, table]
      }
      return current.filter((item) => item !== table)
    })
  }

  useEffect(() => {
    void refreshStats()
  }, [refreshStats])

  const imageBrowserCleanupDisabled = cleanupTarget !== null || isLoading || loadingImageTarget !== null || deletingImageKey !== null
  const browserTargetLabel = browserTarget === 'images' ? '图片缓存' : '表情包缓存'

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="rounded-lg border bg-card p-4 sm:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="flex items-center gap-2 text-base font-semibold sm:text-lg">
              <HardDrive className="h-5 w-5" />
              本地缓存
            </h3>
            <p className="mt-1 text-xs text-muted-foreground sm:text-sm">
              浏览 data 目录中的图片、表情包、日志文件和数据库存储占用。
            </p>
          </div>
          <Button variant="outline" onClick={refreshStats} disabled={isLoading} className="gap-2">
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            刷新
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {(stats?.directories ?? []).map((item) => {
          const imageTarget = getImageTarget(item.key)
          const isBrowserOpen = imageTarget !== null && browserTarget === imageTarget
          const cleanupDisabled = cleanupTarget !== null
            || isLoading
            || loadingImageTarget !== null
            || deletingImageKey !== null
            || loadingLogDirectories
            || deletingLogPath !== null

          return (
            <div key={item.key} className={`space-y-3 ${imageTarget ? '' : 'lg:col-span-2'}`}>
              <DirectoryCard
                item={item}
                isBrowserOpen={isBrowserOpen}
                isLogBrowserOpen={item.key === 'logs' && isLogBrowserOpen}
                cleanupDisabled={cleanupDisabled}
                onBrowse={handleBrowseImages}
                onBrowseLogs={handleBrowseLogs}
                onCleanup={handleDirectoryCleanup}
              />
              {item.key === 'logs' && isLogBrowserOpen && (
                <LogDirectoryListPanel
                  list={logDirectories}
                  isLoading={loadingLogDirectories}
                  deletingPath={deletingLogPath}
                  cleanupDisabled={cleanupDisabled}
                  onRefresh={refreshLogDirectories}
                  onDelete={handleDeleteLogDirectory}
                />
              )}
            </div>
          )
        })}
      </div>

      <Dialog open={browserTarget !== null} onOpenChange={(open) => !open && setBrowserTarget(null)}>
        <DialogContent className="[--dialog-width:72rem]">
          <DialogHeader>
            <DialogTitle>{browserTargetLabel}浏览</DialogTitle>
            <DialogDescription>
              按日期浏览缓存文件，支持单个删除、区间删除和清理最近指定天数以外的数据。
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            {browserTarget && (
              <CacheImageListPanel
                target={browserTarget}
                list={imageLists[browserTarget]}
                filters={imageDateFilters[browserTarget]}
                isLoading={loadingImageTarget === browserTarget}
                deletingKey={deletingImageKey}
                cleanupDisabled={imageBrowserCleanupDisabled}
                onRefresh={handleImageListRefresh}
                onPageChange={handleImagePageChange}
                onDelete={handleDeleteCacheImage}
                onDeleteAll={handleDirectoryCleanup}
                onFilterChange={handleImageDateFilterChange}
                onFilterSubmit={handleImageDateFilterSubmit}
                onFilterClear={handleImageDateFilterClear}
                onDeleteDateRange={handleDeleteCacheImagesByDateRange}
                onDeleteOlderThanRecentDays={handleDeleteCacheImagesOlderThanRecentDays}
              />
            )}
          </DialogBody>
        </DialogContent>
      </Dialog>

      <div className="rounded-lg border bg-card p-4 sm:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 className="flex items-center gap-2 text-base font-semibold sm:text-lg">
              <Database className="h-5 w-5" />
              数据库清理
            </h3>
            <p className="mt-1 text-xs text-muted-foreground sm:text-sm">
              清理数据库中的统计、工具和消息记录，不会删除日志文件、图片、表情文件和配置文件。
            </p>
          </div>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" className="gap-2" disabled={cleanupTarget !== null || isLoading}>
                <Trash2 className="h-4 w-4" />
                数据库清理
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>选择要清理的数据库记录范围</AlertDialogTitle>
                <AlertDialogDescription>
                  数据库当前占用 {formatBytes(stats?.database.total_size ?? 0)}。请手动勾选需要清理的表，默认不会选择任何内容。
                </AlertDialogDescription>
              </AlertDialogHeader>

              <div className="space-y-3">
                {LOG_CLEANUP_OPTIONS.map((option) => {
                  const table = tableStats.get(option.table)
                  const rows = table?.rows ?? 0
                  const checked = selectedLogTables.includes(option.table)
                  const checkboxId = `log-cleanup-${option.table}`
                  return (
                    <label
                      key={option.table}
                      htmlFor={checkboxId}
                      className="flex cursor-pointer items-start gap-3 rounded-md border p-3 hover:bg-muted/50"
                    >
                      <Checkbox
                        id={checkboxId}
                        checked={checked}
                        onCheckedChange={(value) => toggleLogTable(option.table, value === true)}
                        className="mt-0.5"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium">{option.label}</span>
                        <span className="block text-xs text-muted-foreground">{option.description}</span>
                        <span className="mt-1 block text-xs text-muted-foreground">
                          当前 {rows} 条记录，占用 {formatBytes(table?.size ?? 0)}
                        </span>
                      </span>
                    </label>
                  )
                })}
              </div>

              <div className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
                将清理 {selectedLogTables.length} 张表，预计删除 {selectedLogRows} 条记录。删除后数据库文件大小不一定立即缩小。
              </div>

              <AlertDialogFooter>
                <AlertDialogCancel>取消</AlertDialogCancel>
                <AlertDialogAction onClick={handleLogCleanup} disabled={selectedLogTables.length === 0}>
                  确认清理
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <div className="text-xs text-muted-foreground">总体大小</div>
            <div className="text-lg font-semibold">{formatBytes(stats?.database.total_size ?? 0)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">数据库文件</div>
            <div className="text-lg font-semibold">{stats?.database.files.length ?? 0}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">数据表</div>
            <div className="text-lg font-semibold">{stats?.database.tables.length ?? 0}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">总记录数</div>
            <div className="text-lg font-semibold">{totalDatabaseRows}</div>
          </div>
        </div>

        <div className="mt-4 overflow-hidden rounded-md border">
          <div className="grid grid-cols-[minmax(0,1fr)_90px_100px] gap-3 bg-muted/50 px-3 py-2 text-xs font-medium text-muted-foreground sm:grid-cols-[minmax(0,1fr)_120px_140px_90px]">
            <span>表名</span>
            <span className="text-right">记录数</span>
            <span className="text-right">表大小</span>
            <span className="hidden text-right sm:block">来源</span>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {(stats?.database.tables ?? []).map((table) => (
              <div
                key={table.name}
                className="grid grid-cols-[minmax(0,1fr)_90px_100px] gap-3 border-t px-3 py-2 text-sm sm:grid-cols-[minmax(0,1fr)_120px_140px_90px]"
              >
                <span className="min-w-0 truncate font-mono text-xs">{table.name}</span>
                <span className="text-right text-muted-foreground">{table.rows}</span>
                <span className="text-right text-muted-foreground">{formatBytes(table.size)}</span>
                <span className="hidden text-right text-xs text-muted-foreground sm:block">
                  {table.size_source === 'dbstat' ? '实际' : '估算'}
                </span>
              </div>
            ))}
            {(stats?.database.tables ?? []).length === 0 && (
              <div className="border-t p-6 text-center text-sm text-muted-foreground">暂无数据表</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
