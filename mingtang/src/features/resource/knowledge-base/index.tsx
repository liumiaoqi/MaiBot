/**
 * 知识库管理主页面（R4-2-15）
 *
 * 从 dashboard routes/resource/knowledge-base.tsx 搬移 + 组装 4 tabs + 运行时概览区 + 深链接 + 页面三态。
 *
 * 变换：
 * - useToast → sonner
 * - 砍 CorrectionTab + useMemoryCorrection（spec.md §5.6 不做清单）
 * - 砍 graph/timeline/episodes/profiles/maintenance（KnowledgeGraphPage/MemoryTimelineManager/
 *   MemoryEpisodeManager/MemoryProfileManager/MemoryMaintenanceManager 导入和 tab）
 * - MemoryConsoleTab 10 tab 联合 → KnowledgeBaseTab 4 tab 联合（从 types.ts 导入）
 * - 导入路径：./knowledge-base/hooks → ./hooks，./knowledge-base/tabs → ./tabs，
 *   @/components/memory/MemoryDeleteDialog → @/components/biz/memory-delete-dialog
 * - RoutePendingFallback → LoadingSkeleton（mingtang 无 route-pending-fallback）
 * - 主题零黑字（text-black → text-foreground）
 * - tab 切换：10 tab → 4 tab（import/tuning/delete/feedback）
 * - 深链接：砍 correction/graph/timeline/episodes/profiles/maintenance 参数
 * - set-state-in-effect：shouldRenderMemoryTab 懒加载门控用 useRef + Set.has（R4-1 教训 #1）
 * - 保持运行时概览区（useMemoryRuntimeConfig——自检/向量重建）
 */
import { useCallback, useMemo, useState } from 'react'

import {
  Database,
  RefreshCw,
  RotateCcw,
  SlidersHorizontal,
  Upload,
  CheckCircle2,
  CircleAlert,
  FolderOpen,
  HardDrive,
  X,
} from 'lucide-react'

import { MemoryDeleteDialog } from '@/components/biz/memory-delete-dialog'
import { LoadingSkeleton } from '@/components/biz/loading-skeleton'
import { AccentPanel } from '@/components/ui/accent-panel'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { DashboardTabBar, DashboardTabTrigger } from '@/components/ui/dashboard-tabs'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Tabs } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import {
  type MemoryRuntimeConfigPayload,
} from '@/lib/memory-api'

import { useImportForm } from './hooks/useImportForm'
import { useImportQueue } from './hooks/useImportQueue'
import { useMemoryDelete } from './hooks/useMemoryDelete'
import { useMemoryFeedback } from './hooks/useMemoryFeedback'
import { useMemoryRuntimeConfig } from './hooks/useMemoryRuntimeConfig'
import { useMemoryTuning } from './hooks/useMemoryTuning'
import { DeleteTab } from './tabs/DeleteTab'
import { FeedbackTab } from './tabs/FeedbackTab'
import { ImportTab } from './tabs/import/ImportTab'
import { TuningTab } from './tabs/TuningTab'
import {
  KNOWLEDGE_BASE_TABS,
  type KnowledgeBaseDeepLinkState,
  type KnowledgeBaseTab,
} from './types'

const MEMORY_QUICK_START_DISMISSED_KEY = 'memory-quick-start-dismissed'

function parseOptionalNumber(value: string | null): number | undefined {
  if (!value) {
    return undefined
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function readKnowledgeBaseDeepLink(): KnowledgeBaseDeepLinkState {
  if (typeof window === 'undefined') {
    return { tab: 'import' }
  }
  const params = new URLSearchParams(window.location.search)
  const tabParam = params.get('tab') as KnowledgeBaseTab | null
  const tab = tabParam && KNOWLEDGE_BASE_TABS.includes(tabParam) ? tabParam : 'import'
  const taskId = parseOptionalNumber(params.get('task_id'))
  return {
    tab,
    taskId: taskId ? Math.floor(taskId) : undefined,
    operationId: params.get('operation_id') || undefined,
    source: params.get('source') || undefined,
  }
}

function updateKnowledgeBaseDeepLink(
  tab: KnowledgeBaseTab,
  updates: Record<string, string | number | undefined>
) {
  if (typeof window === 'undefined') {
    return
  }
  const params = new URLSearchParams()
  params.set('tab', tab)
  Object.entries(updates).forEach(([key, value]) => {
    if (value !== undefined && String(value).trim()) {
      params.set(key, String(value))
    }
  })
  const nextUrl = `${window.location.pathname}?${params.toString()}${window.location.hash}`
  window.history.replaceState(null, '', nextUrl)
}

function normalizeVectorPoolMode(value: unknown, fallback: 'single' | 'dual' = 'single'): 'single' | 'dual' {
  const mode = typeof value === 'string' ? value.trim().toLowerCase() : ''
  return mode === 'dual' || mode === 'single' ? mode : fallback
}

function formatVectorCount(value?: number): string {
  const count = Number(value ?? 0)
  return Number.isFinite(count) ? String(Math.max(0, count)) : '0'
}

function readProgressNumber(progress: Record<string, unknown> | undefined, key: string): number | undefined {
  const raw = progress?.[key]
  if (raw === undefined || raw === null || raw === '') {
    return undefined
  }
  const value = Number(raw)
  return Number.isFinite(value) ? value : undefined
}

function readProgressRecord(progress: Record<string, unknown> | undefined, key: string): Record<string, unknown> | undefined {
  const value = progress?.[key]
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined
}

function formatMigrationStage(stage?: string): string {
  const normalized = typeof stage === 'string' ? stage.trim() : ''
  const labels: Record<string, string> = {
    initial_delay: '等待启动',
    retry_delay: '等待重试',
    waiting_rebuild_lock: '等待重建锁',
    rebuild_start: '开始重建',
    prepare_rebuild: '准备迁移',
    legacy_source_load: '加载旧池',
    legacy_source_warmup: '预热旧池',
    legacy_source_ready: '旧池就绪',
    legacy_source_incompatible: '旧池不兼容',
    paragraphs_start: '迁移段落',
    paragraphs_done: '段落完成',
    entities_start: '迁移实体',
    entities_done: '实体完成',
    relations_start: '迁移关系',
    relations_done: '关系完成',
    activation_check: '校验双池',
    paragraph_pool_warmup: '预热段落池',
    paragraph_pool_save: '保存段落池',
    graph_pool_warmup: '预热图谱池',
    graph_pool_save: '保存图谱池',
    activate_dirs: '切换目录',
    write_manifest: '写入清单',
    reload_dual_stores: '加载双池',
    dual_backfill: '补齐双池',
    dual_backfill_done: '补齐完成',
    clear_legacy_single_pool: '清理旧池',
    runtime_rebuild: '刷新运行时',
    self_check: '运行自检',
    persist: '持久化',
    completed: '迁移完成',
    failed: '迁移失败',
    cancelled: '已取消',
    exception: '迁移异常',
  }
  return labels[normalized] ?? (normalized || '迁移中')
}

function formatMigrationProgress(progress: Record<string, unknown> | undefined): string {
  const parts: string[] = []
  const paragraphDone = readProgressNumber(progress, 'paragraph_done')
  const paragraphFailed = readProgressNumber(progress, 'paragraph_failed')
  const entityDone = readProgressNumber(progress, 'entity_done')
  const entityFailed = readProgressNumber(progress, 'entity_failed')
  const relationDone = readProgressNumber(progress, 'relation_done')
  const relationFailed = readProgressNumber(progress, 'relation_failed')
  const paragraphCopied = readProgressNumber(readProgressRecord(progress, 'paragraph_migration'), 'copied')
  const entityEncoded = readProgressNumber(readProgressRecord(progress, 'entity_migration'), 'encoded')

  if (paragraphDone !== undefined) {
    parts.push(`段落 ${paragraphDone}${paragraphFailed ? `/${paragraphFailed} 失败` : ''}`)
  }
  if (entityDone !== undefined) {
    parts.push(`实体 ${entityDone}${entityFailed ? `/${entityFailed} 失败` : ''}`)
  }
  if (relationDone !== undefined) {
    parts.push(`关系 ${relationDone}${relationFailed ? `/${relationFailed} 失败` : ''}`)
  }
  if (!parts.length && paragraphCopied !== undefined) {
    parts.push(`已复制 ${paragraphCopied}`)
  }
  if (!parts.length && entityEncoded !== undefined) {
    parts.push(`已编码 ${entityEncoded}`)
  }
  return parts.slice(0, 2).join(' · ')
}

function clampMigrationPercent(value?: number): number | undefined {
  if (value === undefined) {
    return undefined
  }
  return Math.min(100, Math.max(0, value))
}

function formatMigrationEta(seconds?: number): string {
  if (seconds === undefined) {
    return '预计计算中'
  }
  const totalSeconds = Math.max(0, Math.ceil(seconds))
  const minutes = Math.floor(totalSeconds / 60)
  const restSeconds = totalSeconds % 60
  if (minutes < 60) {
    return `预计剩余 ${minutes}分${restSeconds}秒`
  }
  const hours = Math.floor(minutes / 60)
  const restMinutes = minutes % 60
  return `预计剩余 ${hours}小时${restMinutes}分`
}

function formatMigrationSummary(progress: Record<string, unknown> | undefined): string {
  const processed = readProgressNumber(progress, 'processed')
  const total = readProgressNumber(progress, 'total')
  if (processed !== undefined && total !== undefined) {
    const eta = formatMigrationEta(readProgressNumber(progress, 'estimated_remaining_seconds'))
    return `${Math.max(0, Math.floor(processed))}/${Math.max(0, Math.floor(total))} · ${eta}`
  }
  return formatMigrationProgress(progress) || '预计计算中'
}

interface VectorPoolsBadge {
  value: string
  description: string
  progressValue?: number
  progressLabel?: string
  className: string
  iconClassName: string
}

function resolveVectorPoolsBadge(runtimeConfig: MemoryRuntimeConfigPayload): VectorPoolsBadge {
  const vectorPools = runtimeConfig.vector_pools
  const configuredMode = normalizeVectorPoolMode(vectorPools?.configured_mode)
  const effectiveMode = normalizeVectorPoolMode(
    runtimeConfig.vector_pools_effective_mode ?? vectorPools?.effective_mode,
    configuredMode
  )
  const ready = Boolean(runtimeConfig.vector_pools_ready ?? vectorPools?.ready)
  const paragraphCount = formatVectorCount(vectorPools?.paragraph_pool?.num_vectors)
  const graphCount = formatVectorCount(vectorPools?.graph_pool?.num_vectors)
  const singleCount = formatVectorCount(vectorPools?.single_pool?.num_vectors)
  const autoMigration = vectorPools?.auto_migration
  const migrationRunning = Boolean(autoMigration?.running)
  const migrationStage = formatMigrationStage(autoMigration?.stage)
  const migrationSummary = formatMigrationSummary(autoMigration?.progress)
  const migrationPercent = clampMigrationPercent(readProgressNumber(autoMigration?.progress, 'percent'))

  if (effectiveMode === 'dual' && ready) {
    return {
      value: '双池',
      description: `段落 ${paragraphCount} · 图谱 ${graphCount}`,
      className: 'border-cyan-500/25',
      iconClassName: 'text-cyan-500',
    }
  }

  if (configuredMode === 'dual') {
    if (migrationRunning) {
      return {
        value: '双池迁移中',
        description: `${migrationStage} · ${migrationSummary}`,
        progressValue: migrationPercent,
        progressLabel: migrationPercent === undefined ? undefined : `${migrationPercent.toFixed(1)}%`,
        className: 'border-amber-500/25',
        iconClassName: 'text-amber-500',
      }
    }

    return {
      value: '双池未就绪',
      description: `段落 ${paragraphCount} · 图谱 ${graphCount}`,
      className: 'border-amber-500/25',
      iconClassName: 'text-amber-500',
    }
  }

  return {
    value: '单池',
    description: `单池向量 ${singleCount}`,
    className: 'border-cyan-500/25',
    iconClassName: 'text-cyan-500',
  }
}

export function KnowledgeBasePage() {
  const [deepLink] = useState<KnowledgeBaseDeepLinkState>(readKnowledgeBaseDeepLink)
  const [activeTab, setActiveTab] = useState<KnowledgeBaseTab>(deepLink.tab)
  const [quickStartVisible, setQuickStartVisible] = useState(() => {
    if (typeof window === 'undefined') {
      return true
    }
    return window.localStorage.getItem(MEMORY_QUICK_START_DISMISSED_KEY) !== 'true'
  })

  // shouldRenderMemoryTab 懒加载门控：useState + 渲染期 setState（R4-1 教训 #1：避免 effect setState）
  // 切到过的 tab 保留 DOM（避免表单本地 state 丢失），未切到的不渲染
  const [visitedMemoryTabs, setVisitedMemoryTabs] = useState<Set<KnowledgeBaseTab>>(
    () => new Set([deepLink.tab])
  )
  // 渲染期更新（非 effect）—— React 19 允许渲染期 setState，会被合并到当前渲染
  if (!visitedMemoryTabs.has(activeTab)) {
    setVisitedMemoryTabs((current) => {
      const next = new Set(current)
      next.add(activeTab)
      return next
    })
  }

  const importQueue = useImportQueue({
    active: activeTab === 'import',
    // 重试沿用表单当前公共参数作 overrides（拆分前 retry 直接读这些 state）
    buildRetryOverrides: () => importForm.buildCommonImportPayload(),
  })
  const importForm = useImportForm({
    active: activeTab === 'import',
    onCreated: (taskId) => importQueue.afterCreated(taskId),
  })

  // 运行时配置：服务于概览区，默认即拉取（非懒加载）；自检与向量重建一并下沉
  const memoryRuntime = useMemoryRuntimeConfig()
  const { runtimeConfig } = memoryRuntime

  // 删除领域：来源/操作列表懒加载、操作详情、源选择、删除预览-执行（usePendingOperation）、恢复
  const memoryDelete = useMemoryDelete({
    active: activeTab === 'delete',
    initialSourceSearch: deepLink.source ?? '',
    initialOperationSearch: deepLink.operationId ?? deepLink.source ?? '',
    initialOperationId: deepLink.operationId ?? '',
    initialItemSearch: deepLink.source ?? '',
  })

  // 纠错领域：纠错历史懒加载、任务详情、行为日志分页、回退；回退后刷新来源与运行时配置
  const memoryFeedback = useMemoryFeedback({
    active: activeTab === 'feedback',
    initialSearch: deepLink.taskId ? String(deepLink.taskId) : '',
    initialTaskId: deepLink.taskId ?? 0,
    onRuntimeChanged: () => memoryRuntime.refreshRuntimeConfig(),
    onSourcesChanged: () => memoryDelete.refreshSources(),
  })

  // 调优领域：调优配置/任务列表懒加载、调优参数、创建任务、应用最佳；应用后刷新运行时配置
  const memoryTuning = useMemoryTuning({
    active: activeTab === 'tuning',
    onRuntimeChanged: () => memoryRuntime.refreshRuntimeConfig(),
  })

  const switchMemoryTab = useCallback(
    (tab: KnowledgeBaseTab, query: Record<string, string | number | undefined> = {}) => {
      setActiveTab(tab)
      updateKnowledgeBaseDeepLink(tab, query)
    },
    []
  )

  const loadPage = useCallback(async () => {
    try {
      await memoryRuntime.refreshRuntimeConfig()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载长期记忆控制台失败')
    }
  }, [memoryRuntime])

  const runtimeBadges = useMemo(() => {
    if (!runtimeConfig) {
      return []
    }
    const vectorPoolsBadge = resolveVectorPoolsBadge(runtimeConfig)
    return [
      {
        label: '运行状态',
        value: runtimeConfig.runtime_ready ? '就绪' : '未就绪',
        description: runtimeConfig.embedding_degraded ? 'Embedding 降级运行' : '运行时检查通过',
        progressValue: undefined,
        progressLabel: undefined,
        icon: runtimeConfig.runtime_ready ? CheckCircle2 : CircleAlert,
        className: runtimeConfig.runtime_ready ? 'border-emerald-500/25' : 'border-amber-500/25',
        iconClassName: runtimeConfig.runtime_ready ? 'text-emerald-500' : 'text-amber-500',
      },
      {
        label: 'Embedding 维度',
        value: String(runtimeConfig.embedding_dimension),
        description: runtimeConfig.relation_vectors_enabled ? '关系向量已启用' : '关系向量未启用',
        progressValue: undefined,
        progressLabel: undefined,
        icon: HardDrive,
        className: 'border-sky-500/25',
        iconClassName: 'text-sky-500',
      },
      {
        label: '向量池',
        value: vectorPoolsBadge.value,
        description: vectorPoolsBadge.description,
        progressValue: vectorPoolsBadge.progressValue,
        progressLabel: vectorPoolsBadge.progressLabel,
        icon: Database,
        className: vectorPoolsBadge.className,
        iconClassName: vectorPoolsBadge.iconClassName,
      },
      {
        label: '数据目录',
        value: runtimeConfig.data_dir,
        description: '长期记忆存储位置',
        progressValue: undefined,
        progressLabel: undefined,
        icon: FolderOpen,
        className: 'border-violet-500/25',
        iconClassName: 'text-violet-500',
      },
    ]
  }, [runtimeConfig])

  const dismissQuickStart = useCallback(() => {
    window.localStorage.setItem(MEMORY_QUICK_START_DISMISSED_KEY, 'true')
    setQuickStartVisible(false)
  }, [])

  const shouldRenderMemoryTab = (tab: KnowledgeBaseTab) =>
    activeTab === tab || visitedMemoryTabs.has(tab)

  // 页面三态：加载态（runtimeLoading → LoadingSkeleton）
  if (memoryRuntime.runtimeLoading) {
    return <LoadingSkeleton rows={6} message="正在加载长期记忆控制台..." />
  }

  return (
    <div className="bg-background flex h-full flex-col">
      <div className="flex-1 overflow-auto">
        <div className="memory-console-density mx-auto flex w-full max-w-[1800px] flex-col gap-4 px-4 py-4 xl:px-5">
          <div className="hidden">
            <Button variant="outline" size="sm" onClick={() => void loadPage()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              刷新数据
            </Button>
          </div>
          {/* 运行时状态条 —— 紧凑、常驻、一眼看完 */}
          {runtimeBadges.length > 0 ? (
            <AccentPanel
              showRetroStripes={false}
              data-memory-runtime-status="true"
              className="border-border/60 border bg-transparent"
              contentClassName="p-3"
            >
              <div className="mb-2 flex items-center justify-end gap-2">
                {runtimeConfig?.vector_rebuild_required ? (
                  <Button
                    variant="destructive"
                    size="sm"
                    className="h-6 px-2 text-[11px]"
                    onClick={() => void memoryRuntime.openVectorRebuildDialog()}
                    disabled={memoryRuntime.vectorRebuilding}
                  >
                    <RotateCcw
                      className={cn(
                        'mr-1 h-3 w-3',
                        memoryRuntime.vectorRebuilding && 'animate-spin'
                      )}
                    />
                    重建向量
                  </Button>
                ) : null}
                <Button
                  variant="outline"
                  size="sm"
                  className="h-6 px-2 text-[11px]"
                  onClick={() => void loadPage()}
                >
                  <RefreshCw className="mr-1 h-3 w-3" />
                  刷新数据
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-[11px]"
                  onClick={() => void memoryRuntime.refreshSelfCheck()}
                  disabled={memoryRuntime.refreshingCheck}
                >
                  <RefreshCw
                    className={cn('mr-1 h-3 w-3', memoryRuntime.refreshingCheck && 'animate-spin')}
                  />
                  自检
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-1.5 sm:gap-2 lg:grid-cols-4">
                {runtimeBadges.map((item) => (
                  <div
                    key={item.label}
                    className={cn(
                      'min-w-0 overflow-hidden border bg-transparent px-2 py-1.5 transition-colors sm:flex sm:items-center sm:gap-2 sm:px-2.5',
                      item.className
                    )}
                  >
                    <div className="mb-1 w-fit flex-none border bg-transparent p-1 sm:mb-0">
                      <item.icon className={cn('h-3.5 w-3.5', item.iconClassName)} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-muted-foreground truncate text-[10px] leading-tight font-medium">
                        {item.label}
                      </div>
                      <div
                        className="truncate text-xs leading-tight font-semibold"
                        title={item.value}
                      >
                        {item.value}
                      </div>
                      <div
                        className={cn(
                          'text-muted-foreground mt-0.5 truncate text-[10px]',
                          item.progressValue !== undefined ? 'block' : 'hidden xl:block'
                        )}
                      >
                        {item.description}
                      </div>
                      {item.progressValue !== undefined ? (
                        <div className="mt-1.5 flex items-center gap-1.5">
                          <Progress value={item.progressValue} className="h-1 flex-1" />
                          <span className="text-muted-foreground text-[10px] leading-none tabular-nums">
                            {item.progressLabel}
                          </span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </AccentPanel>
          ) : null}

          <Dialog
            open={memoryRuntime.vectorRebuildDialogOpen}
            onOpenChange={memoryRuntime.setVectorRebuildDialogOpen}
          >
            <DialogContent>
              <DialogHeader>
                <DialogTitle>重建全部向量</DialogTitle>
                <DialogDescription>
                  将使用当前 embedding
                  配置重新生成段落、实体和已启用的关系向量，期间检索会临时降级（会对嵌入模型造成大量请求！）
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-3 text-sm">
                <Alert variant={runtimeConfig?.vector_rebuild_required ? 'destructive' : 'default'}>
                  <AlertDescription>
                    {runtimeConfig?.vector_rebuild_message ||
                      '这个操作会替换现有向量库，适合更换 embedding 模型或维度后执行。'}
                  </AlertDescription>
                </Alert>
                <div className="grid gap-2 sm:grid-cols-3">
                  {(['paragraphs', 'entities', 'relations'] as const).map((key) => (
                    <div key={key} className="bg-muted/30 rounded-lg border p-3">
                      <div className="text-muted-foreground text-xs">
                        {key === 'paragraphs' ? '段落' : key === 'entities' ? '实体' : '关系'}
                      </div>
                      <div className="mt-1 text-xl font-semibold">
                        {memoryRuntime.vectorRebuildPreview?.[key] ?? '-'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => memoryRuntime.setVectorRebuildDialogOpen(false)}
                  disabled={memoryRuntime.vectorRebuilding}
                >
                  取消
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => void memoryRuntime.confirmVectorRebuild()}
                  disabled={memoryRuntime.vectorRebuilding}
                >
                  <RotateCcw
                    className={cn('mr-2 h-4 w-4', memoryRuntime.vectorRebuilding && 'animate-spin')}
                  />
                  确认重建
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* 快速开始 Hero —— 给新用户明确的"先做什么" */}
          {quickStartVisible && (
            <AccentPanel
              showRetroStripes={false}
              className="border-primary/20 from-primary/10 via-primary/5 relative overflow-hidden rounded-xl border bg-gradient-to-br to-transparent shadow-sm"
              contentClassName="p-4 pr-11"
            >
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="text-muted-foreground hover:text-foreground absolute top-3 right-3 h-7 w-7"
                onClick={dismissQuickStart}
                aria-label="关闭快速开始"
                title="关闭快速开始"
              >
                <X className="h-4 w-4" />
              </Button>
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="space-y-1.5 lg:max-w-sm">
                  <div className="text-primary text-[11px] font-medium tracking-[0.18em] uppercase">
                    快速开始
                  </div>
                  <h2 className="text-lg leading-tight font-semibold">先从这两件事入手</h2>
                  <p className="text-muted-foreground text-sm">
                    不知道该做什么？挑一个最常用的入口，下面的标签页里有更详细的设置。
                  </p>
                </div>
                <div className="grid w-full gap-2 sm:grid-cols-2 lg:max-w-2xl">
                  <button
                    type="button"
                    onClick={() => switchMemoryTab('import')}
                    className="group border-border/70 bg-background/80 hover:border-primary/50 hover:bg-background flex items-start gap-2 rounded-lg border p-3 text-left transition hover:shadow-md"
                  >
                    <div className="bg-primary/10 text-primary flex-none rounded-lg p-2 transition-transform group-hover:scale-105">
                      <Upload className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold">导入资料</div>
                      <div className="text-muted-foreground mt-0.5 text-xs leading-relaxed">
                        把文件、聊天记录写进记忆库
                      </div>
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => switchMemoryTab('tuning')}
                    className="group border-border/70 bg-background/80 hover:border-primary/50 hover:bg-background flex items-start gap-2 rounded-lg border p-3 text-left transition hover:shadow-md"
                  >
                    <div className="flex-none rounded-lg bg-amber-500/10 p-2 text-amber-500 transition-transform group-hover:scale-105">
                      <SlidersHorizontal className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold">检索调优</div>
                      <div className="text-muted-foreground mt-0.5 text-xs leading-relaxed">
                        让回忆变得更准、更聪明
                      </div>
                    </div>
                  </button>
                </div>
              </div>
            </AccentPanel>
          )}

          <Tabs
            value={activeTab}
            onValueChange={(value) => switchMemoryTab(value as KnowledgeBaseTab)}
            className="space-y-3"
          >
            <div className="border-border/40 -mx-4 border-b px-4 pt-0 pb-1.5 xl:-mx-5 xl:px-5">
              <div className="flex flex-wrap items-center gap-2">
                <DashboardTabBar
                  variant="grid"
                  className="w-fit max-w-full auto-cols-max grid-flow-col"
                >
                  {[
                    { value: 'import', label: '导入', description: '创建并管理导入任务' },
                    { value: 'tuning', label: '调优', description: '检索策略调优' },
                    { value: 'delete', label: '删除', description: '批量删除与历史回溯' },
                    { value: 'feedback', label: '纠错历史', description: '查看反馈与回滚' },
                  ].map((item) => (
                    <DashboardTabTrigger
                      key={item.value}
                      value={item.value}
                      title={item.description}
                      className="px-3 text-xs"
                    >
                      {item.label}
                    </DashboardTabTrigger>
                  ))}
                </DashboardTabBar>
              </div>
            </div>

            {/* 导入面板的数据由 useImportQueue/useImportForm 自管加载（useQuery enabled:active），
                不再走懒加载占位门控；表单即时可交互，任务列表异步填充 */}
            {shouldRenderMemoryTab('import') && <ImportTab queue={importQueue} form={importForm} />}

            {/* 调优面板数据由 useMemoryTuning 自管加载（enabled:active），不再走懒加载占位门控 */}
            {shouldRenderMemoryTab('tuning') && <TuningTab tuning={memoryTuning} />}

            {/* 删除面板数据由 useMemoryDelete 自管加载（enabled:active），不再走懒加载占位门控 */}
            {shouldRenderMemoryTab('delete') && <DeleteTab delete={memoryDelete} />}

            {/* 纠错面板数据由 useMemoryFeedback 自管加载（enabled:active），不再走懒加载占位门控 */}
            {shouldRenderMemoryTab('feedback') && <FeedbackTab feedback={memoryFeedback} />}
          </Tabs>
        </div>
      </div>

      <MemoryDeleteDialog
        open={memoryDelete.deleteDialogOpen}
        onOpenChange={memoryDelete.closeDeleteDialog}
        title={memoryDelete.deleteDialogTitle}
        description={memoryDelete.deleteDialogDescription}
        preview={memoryDelete.deletePreview}
        result={memoryDelete.deleteResult}
        loadingPreview={memoryDelete.deletePreviewLoading}
        executing={memoryDelete.deleteExecuting}
        restoring={memoryDelete.deleteRestoring}
        error={memoryDelete.deletePreviewError}
        onExecute={() => void memoryDelete.executePendingDelete()}
        onRestore={() =>
          void (memoryDelete.deleteResult?.operation_id
            ? memoryDelete.restoreDeleteOperation(memoryDelete.deleteResult.operation_id)
            : Promise.resolve())
        }
      />

      <Dialog
        open={memoryFeedback.feedbackRollbackDialogOpen}
        onOpenChange={memoryFeedback.setFeedbackRollbackDialogOpen}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>回退本次纠错</DialogTitle>
            <DialogDescription>
              这会恢复旧关系状态、隐藏本次纠错写入的段落，并重新触发 Episode / Profile 的异步修复。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="bg-muted/20 rounded-lg border p-3 text-sm">
              <div className="font-medium break-words">
                {memoryFeedback.selectedFeedbackResolved?.query_text || '无查询文本'}
              </div>
              <div className="text-muted-foreground mt-1 font-mono text-[11px] break-all">
                {memoryFeedback.selectedFeedbackResolved?.query_tool_id}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="feedback-rollback-reason">回退原因</Label>
              <Textarea
                id="feedback-rollback-reason"
                value={memoryFeedback.feedbackRollbackReason}
                onChange={(event) => memoryFeedback.setFeedbackRollbackReason(event.target.value)}
                placeholder="可选，建议填写本次人工回退原因"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => memoryFeedback.setFeedbackRollbackDialogOpen(false)}
              disabled={memoryFeedback.feedbackRollingBack}
            >
              取消
            </Button>
            <Button
              onClick={() => void memoryFeedback.executeFeedbackRollback()}
              disabled={memoryFeedback.feedbackRollingBack}
            >
              {memoryFeedback.feedbackRollingBack ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  回退中
                </>
              ) : (
                <>
                  <RotateCcw className="mr-2 h-4 w-4" />
                  确认回退
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}