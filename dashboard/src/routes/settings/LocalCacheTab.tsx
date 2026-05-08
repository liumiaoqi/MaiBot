import { Database, HardDrive, Image, RefreshCw, Sparkles, Trash2 } from 'lucide-react'
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
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { useToast } from '@/hooks/use-toast'
import {
  cleanupLocalCache,
  getLocalCacheStats,
  type CacheDirectoryStats,
  type LocalCacheCleanupTarget,
  type LocalCacheStats,
  type LogCleanupTable,
} from '@/lib/system-api'

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
  if (cacheKey === 'emoji' || cacheKey === 'emoji_thumbnails') {
    return <Sparkles className="h-4 w-4 text-primary" />
  }
  return <HardDrive className="h-4 w-4 text-primary" />
}

function DirectoryCard({
  item,
  cleanupDisabled,
  onCleanup,
}: {
  item: CacheDirectoryStats
  cleanupDisabled: boolean
  onCleanup: (target: 'images' | 'emoji' | 'log_files') => void
}) {
  const cleanupTarget = item.key === 'images' ? 'images' : item.key === 'emoji' ? 'emoji' : item.key === 'logs' ? 'log_files' : null
  const cleanupDescription = cleanupTarget === 'log_files'
    ? '这会删除 logs 目录中的日志文件。操作不可撤销。'
    : '这会删除对应目录中的文件，并移除数据库里的相关记录。操作不可撤销。'

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
        {cleanupTarget && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2" disabled={cleanupDisabled}>
                <Trash2 className="h-4 w-4" />
                清理
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>确认清理{item.label}？</AlertDialogTitle>
                <AlertDialogDescription>
                  {cleanupDescription}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>取消</AlertDialogCancel>
                <AlertDialogAction onClick={() => onCleanup(cleanupTarget)}>确认清理</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
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

  const tableRows = useMemo(() => {
    const rows = new Map<string, number>()
    for (const table of stats?.database.tables ?? []) {
      rows.set(table.name, table.rows)
    }
    return rows
  }, [stats?.database.tables])

  const selectedLogRows = selectedLogTables.reduce((total, table) => total + (tableRows.get(table) ?? 0), 0)

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

  const handleDirectoryCleanup = async (target: 'images' | 'emoji' | 'log_files') => {
    setCleanupTarget(target)
    try {
      const result = await cleanupLocalCache(target)
      await refreshStats()
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
              浏览 data 目录中的图片、表情包和数据库存储占用。
            </p>
          </div>
          <Button variant="outline" onClick={refreshStats} disabled={isLoading} className="gap-2">
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            刷新
          </Button>
        </div>
      </div>

      <div className="grid gap-4">
        {(stats?.directories ?? []).map((item) => (
          <DirectoryCard
            key={item.key}
            item={item}
            cleanupDisabled={cleanupTarget !== null || isLoading}
            onCleanup={handleDirectoryCleanup}
          />
        ))}
      </div>

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
                  const rows = tableRows.get(option.table) ?? 0
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
                        <span className="mt-1 block text-xs text-muted-foreground">当前 {rows} 条记录</span>
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
      </div>
    </div>
  )
}
