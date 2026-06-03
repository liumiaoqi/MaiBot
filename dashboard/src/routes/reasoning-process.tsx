import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  ArrowLeft,
  Clock,
  Code2,
  Copy,
  Cpu,
  FileCode2,
  FileJson,
  FileText,
  Layers,
  RefreshCw,
  Search,
  Timer,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ThinkingIllustration } from '@/components/ui/thinking-illustration'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import {
  getReasoningPromptFile,
  getReasoningPromptHtmlUrl,
  listReasoningPromptFiles,
  listReasoningPromptStages,
  type ReasoningPromptFile,
  type ReasoningPromptSessionInfo,
  type ReasoningPromptStageInfo,
} from '@/lib/reasoning-process-api'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 50
const AUTO_SESSION = 'auto'
const PRIMARY_STAGE_NAMES = ['timing_gate', 'planner', 'replyer']
const STAGE_LABELS: Record<string, string> = {
  emotion: '情绪分析',
  expression_learner: '表达学习',
  planner: '规划器',
  reply_effect_judge: '回复效果评估',
  replyer: '回复器',
  timing_gate: '时机判断',
}

type StructuredPromptMessage = {
  index?: number
  role?: string
  content?: unknown
  content_text?: string
  tool_call_id?: string
  tool_calls?: unknown[]
}

type StructuredPromptPayload = {
  schema_version?: number
  request?: {
    kind?: string
    selection_reason?: string
  }
  metadata?: {
    model_name?: string
    duration_ms?: number
  }
  messages?: StructuredPromptMessage[]
  output?: {
    title?: string
    content?: unknown
    content_text?: string
  } | null
  tool_definitions?: unknown[]
  text_dump?: string
}

function formatStageName(stage: string): string {
  return STAGE_LABELS[stage] ?? stage
}

function formatTime(timestamp: number | null, modifiedAt: number): string {
  const value = timestamp ? timestamp : modifiedAt * 1000
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function formatDurationMs(durationMs: number | null): string {
  if (durationMs === null || !Number.isFinite(durationMs)) return ''
  if (durationMs < 1000) return `${durationMs.toFixed(durationMs >= 100 ? 0 : 1)} ms`
  return `${(durationMs / 1000).toFixed(2)} s`
}

function getReasoningMetadataText(item: ReasoningPromptFile): string {
  const parts: string[] = []
  if (item.model_name) {
    parts.push(`模型：${item.model_name}`)
  }
  const durationText = formatDurationMs(item.duration_ms)
  if (durationText) {
    parts.push(`耗时：${durationText}`)
  }
  return parts.join(' · ')
}

function stringifyStructuredValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return ''
  return JSON.stringify(value, null, 2)
}

function parseStructuredPrompt(content: string): StructuredPromptPayload | null {
  if (!content.trim()) return null
  try {
    const payload = JSON.parse(content) as unknown
    if (payload && typeof payload === 'object') return payload as StructuredPromptPayload
  } catch {
    return null
  }
  return null
}

function formatSessionType(chatType: string): string {
  if (chatType === 'group') return '群聊'
  if (chatType === 'private') return '私聊'
  return '未知类型'
}

function getSessionDisplayName(
  sessionName: string,
  sessionInfo?: ReasoningPromptSessionInfo,
  fallbackName?: string | null
): string {
  return sessionInfo?.display_name || fallbackName || sessionName
}

function getSessionSubtitle(sessionInfo?: ReasoningPromptSessionInfo): string {
  if (!sessionInfo) return ''

  const parts = []
  if (sessionInfo.platform && sessionInfo.target_id) {
    parts.push(
      `${sessionInfo.platform} · ${formatSessionType(sessionInfo.chat_type)} · ${sessionInfo.target_id}`
    )
  }
  if (sessionInfo.resolved_session_id) {
    parts.push(`会话 ${sessionInfo.resolved_session_id.slice(0, 8)}`)
  } else {
    parts.push('未解析到真实会话')
  }
  return parts.join(' · ')
}

interface ReasoningProcessPageProps {
  embedded?: boolean
  toolbarContainerId?: string
  toolbarVisible?: boolean
}

export function ReasoningProcessPage({
  embedded = false,
  toolbarContainerId,
  toolbarVisible = true,
}: ReasoningProcessPageProps) {
  const { toast } = useToast()
  const [items, setItems] = useState<ReasoningPromptFile[]>([])
  const [stages, setStages] = useState<string[]>([])
  const [stageInfos, setStageInfos] = useState<ReasoningPromptStageInfo[]>([])
  const [sessions, setSessions] = useState<string[]>([])
  const [sessionInfos, setSessionInfos] = useState<ReasoningPromptSessionInfo[]>([])
  const [stage, setStage] = useState('planner')
  const [session, setSession] = useState(AUTO_SESSION)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [refreshKey, setRefreshKey] = useState(0)
  const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState<ReasoningPromptFile | null>(null)
  const [textContent, setTextContent] = useState('')
  const [jsonContent, setJsonContent] = useState('')
  const [activePreview, setActivePreview] = useState<'structured' | 'text' | 'html'>('structured')
  const [htmlPreviewUrl, setHtmlPreviewUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [contentLoading, setContentLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [browsingStage, setBrowsingStage] = useState(false)
  const [toolbarRoot, setToolbarRoot] = useState<HTMLElement | null>(null)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const stageCards = useMemo(() => {
    if (stageInfos.length > 0) return stageInfos
    return stages.map((name) => ({ name, session_count: 0, latest_modified_at: 0 }))
  }, [stageInfos, stages])
  const primaryStageCards = useMemo(() => {
    const stageInfoByName = new Map(stageCards.map((item) => [item.name, item]))
    return PRIMARY_STAGE_NAMES.flatMap((name) => {
      const item = stageInfoByName.get(name)
      return item ? [item] : []
    })
  }, [stageCards])
  const secondaryStageCards = useMemo(() => {
    return stageCards.filter((item) => !PRIMARY_STAGE_NAMES.includes(item.name))
  }, [stageCards])
  const sessionInfoByName = useMemo(() => {
    return new Map(sessionInfos.map((item) => [item.name, item]))
  }, [sessionInfos])
  const structuredPrompt = useMemo(() => parseStructuredPrompt(jsonContent), [jsonContent])

  useEffect(() => {
    setToolbarRoot(toolbarContainerId ? document.getElementById(toolbarContainerId) : null)
  }, [toolbarContainerId])

  useEffect(() => {
    let ignore = false

    async function loadStages() {
      setLoading(true)
      setError(null)
      try {
        const data = await listReasoningPromptStages()
        if (ignore) return
        setStages(data.stages)
        setStageInfos(data.stage_infos ?? [])
      } catch (err) {
        if (!ignore) setError(err instanceof Error ? err.message : '加载推理过程类型失败')
      } finally {
        if (!ignore) setLoading(false)
      }
    }

    if (!browsingStage) {
      void loadStages()
    }

    return () => {
      ignore = true
    }
  }, [browsingStage, refreshKey])

  useEffect(() => {
    let ignore = false

    async function loadFiles() {
      if (!browsingStage) return
      setLoading(true)
      setError(null)
      try {
        const data = await listReasoningPromptFiles({
          stage,
          session,
          search,
          page,
          pageSize: PAGE_SIZE,
        })
        if (ignore) return
        setItems(data.items)
        setStages(data.stages)
        setStageInfos(data.stage_infos ?? [])
        setSessions(data.sessions)
        setSessionInfos(data.session_infos ?? [])
        if (data.selected_session && data.selected_session !== session) {
          setSession(data.selected_session)
        }
        setTotal(data.total)
        setSelected((current) => {
          if (
            current &&
            data.items.some(
              (item) =>
                item.stem === current.stem &&
                item.stage === current.stage &&
                item.session_id === current.session_id
            )
          ) {
            return current
          }
          return null
        })
      } catch (err) {
        if (!ignore) setError(err instanceof Error ? err.message : '加载推理过程失败')
      } finally {
        if (!ignore) setLoading(false)
      }
    }

    void loadFiles()
    return () => {
      ignore = true
    }
  }, [browsingStage, page, refreshKey, search, session, stage])

  useEffect(() => {
    let ignore = false

    async function loadContent() {
      if (!selected?.text_path) {
        setTextContent('')
      } else {
        setContentLoading(true)
        try {
          const data = await getReasoningPromptFile(selected.text_path)
          if (!ignore) setTextContent(data.content)
        } catch (err) {
          if (!ignore) {
            setTextContent(err instanceof Error ? err.message : '读取文本失败')
          }
        } finally {
          if (!ignore) setContentLoading(false)
        }
      }

      if (!selected?.json_path) {
        setJsonContent('')
        return
      }

      setContentLoading(true)
      try {
        const data = await getReasoningPromptFile(selected.json_path)
        if (!ignore) setJsonContent(data.content)
      } catch (err) {
        if (!ignore) {
          setJsonContent('')
          setTextContent((current) => current || (err instanceof Error ? err.message : '读取结构化内容失败'))
        }
      } finally {
        if (!ignore) setContentLoading(false)
      }
    }

    async function loadHtmlPreviewUrl() {
      if (!selected?.html_path) {
        setHtmlPreviewUrl('')
        return
      }
      const url = await getReasoningPromptHtmlUrl(selected.html_path)
      if (!ignore) setHtmlPreviewUrl(url)
    }

    if (selected?.json_path) {
      setActivePreview('structured')
    } else if (selected?.html_path && !selected.text_path) {
      setActivePreview('html')
    } else {
      setActivePreview('text')
    }
    loadContent()
    loadHtmlPreviewUrl()
    return () => {
      ignore = true
    }
  }, [selected])

  function resetToFirstPage(nextAction: () => void) {
    nextAction()
    setPage(1)
  }

  function enterStage(nextStage: string) {
    resetToFirstPage(() => {
      setStage(nextStage)
      setSession(AUTO_SESSION)
      setSearch('')
      setItems([])
      setSessions([])
      setSessionInfos([])
      setTotal(0)
      setSelected(null)
      setBrowsingStage(true)
    })
  }

  async function handleCopyPrompt() {
    const copyContent = textContent || structuredPrompt?.text_dump || jsonContent
    if (!copyContent || contentLoading) {
      toast({
        title: '暂无可复制内容',
        description: '请先选择一条包含 prompt 内容的记录',
        variant: 'destructive',
      })
      return
    }

    try {
      await navigator.clipboard.writeText(copyContent)
      toast({
        title: '已复制完整 Prompt',
        description: selected
          ? `${formatStageName(selected.stage)}/${getSessionDisplayName(
              selected.session_id,
              selectedSessionInfo,
              selected.session_display_name
            )}/${selected.stem}`
          : undefined,
      })
    } catch (err) {
      toast({
        title: '复制失败',
        description: err instanceof Error ? err.message : '请手动选择文本复制',
        variant: 'destructive',
      })
    }
  }

  const selectedSessionInfo = selected ? sessionInfoByName.get(selected.session_id) : undefined
  const selectedMetadataText = selected ? getReasoningMetadataText(selected) : ''
  const selectedDurationText = selected ? formatDurationMs(selected.duration_ms) : ''
  const renderRefreshButton = () => (
    <Button
      variant="outline"
      size="sm"
      onClick={() => setRefreshKey((current) => current + 1)}
      disabled={loading}
      className="h-10 shrink-0 justify-start"
    >
      <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
      刷新
    </Button>
  )
  const renderBrowsingControls = (inToolbar = false) => (
    <>
      <Button
        variant="outline"
        size="sm"
        className="h-10 shrink-0 justify-start"
        onClick={() => setBrowsingStage(false)}
      >
        <ArrowLeft className="h-4 w-4" />
        类型
      </Button>

      <Select
        value={session}
        onValueChange={(value) => resetToFirstPage(() => setSession(value))}
        disabled={sessions.length === 0 && loading}
      >
        <SelectTrigger className={cn('h-10', inToolbar ? 'w-[240px]' : undefined)}>
          <SelectValue placeholder="会话" />
        </SelectTrigger>
        <SelectContent>
          {session === AUTO_SESSION && (
            <SelectItem value={AUTO_SESSION}>自动选择最近会话</SelectItem>
          )}
          {sessions.map((item) => {
            const sessionInfo = sessionInfoByName.get(item)
            return (
              <SelectItem key={item} value={item}>
                <div className="min-w-0">
                  <div className="truncate">{getSessionDisplayName(item, sessionInfo)}</div>
                  {sessionInfo && (
                    <div className="text-muted-foreground truncate text-xs">
                      {getSessionSubtitle(sessionInfo)}
                    </div>
                  )}
                </div>
              </SelectItem>
            )
          })}
        </SelectContent>
      </Select>

      <div className={cn('relative', inToolbar ? 'min-w-[300px] flex-1 max-w-[520px]' : undefined)}>
        <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
        <Input
          value={search}
          onChange={(event) => resetToFirstPage(() => setSearch(event.target.value))}
          className="h-10 pl-9"
          placeholder="搜索会话显示名、真实会话、文件名或 replyer 回复内容"
        />
      </div>
    </>
  )
  const toolbarContent = (
    <div className="flex w-full min-w-0 flex-wrap items-center justify-end gap-2">
      {renderRefreshButton()}
      {browsingStage && renderBrowsingControls(true)}
    </div>
  )
  const toolbarPortal = embedded && toolbarVisible && toolbarRoot ? createPortal(toolbarContent, toolbarRoot) : null
  const renderStageCard = (item: ReasoningPromptStageInfo, compact = false) => (
    <button
      key={item.name}
      type="button"
      onClick={() => enterStage(item.name)}
      className={cn(
        'flex flex-col justify-between rounded-md border text-left transition-colors',
        'hover:border-primary hover:bg-primary/10 focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none',
        compact ? 'min-h-20 p-3' : 'min-h-32 p-4'
      )}
    >
      <div className={compact ? 'space-y-1.5' : 'space-y-2'}>
        <Badge variant="secondary" className="w-fit">
          {item.name}
        </Badge>
        <div className={cn('text-foreground font-semibold', compact ? 'text-sm' : 'text-base')}>
          {formatStageName(item.name)}
        </div>
      </div>
      <div className={cn('text-muted-foreground text-xs', compact ? 'mt-2' : 'mt-4')}>
        {item.session_count} 个会话
        {item.latest_modified_at > 0 ? ` · 最新 ${formatTime(null, item.latest_modified_at)}` : ''}
      </div>
    </button>
  )

  return (
    <div className={cn('flex h-full min-h-0 flex-col gap-3 overflow-hidden', embedded ? 'p-0' : 'p-3 lg:p-4')}>
      {toolbarPortal}

      {!embedded && (
        <div className="flex flex-shrink-0 items-start justify-between gap-3">
          <div>
            <h1 className="text-foreground text-xl font-semibold tracking-normal">推理过程</h1>
            <p className="text-muted-foreground text-sm">浏览 logs/maisaka_prompt 下的 prompt 记录</p>
          </div>
          {renderRefreshButton()}
        </div>
      )}

      {!embedded && browsingStage && (
        <div className="grid flex-shrink-0 grid-cols-1 gap-2 md:grid-cols-[auto_minmax(220px,320px)_1fr]">
          {renderBrowsingControls()}
        </div>
      )}

      {error && (
        <div className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm">
          {error}
        </div>
      )}

      {!browsingStage ? (
        <div className="bg-background flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border">
          <div className="flex h-12 flex-shrink-0 items-center gap-2 border-b px-4">
            <Layers className="text-muted-foreground h-4 w-4" />
            <div className="text-sm font-medium">选择推理类型</div>
          </div>
          <ScrollArea className="min-h-0 flex-1">
            <div className="space-y-4 p-3">
              {primaryStageCards.length > 0 && (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {primaryStageCards.map((item) => renderStageCard(item))}
                </div>
              )}
              {secondaryStageCards.length > 0 && (
                <div className="border-t pt-3">
                  <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                    {secondaryStageCards.map((item) => renderStageCard(item, true))}
                  </div>
                </div>
              )}
              {!loading && stageCards.length === 0 && (
                <div className="text-muted-foreground px-3 py-10 text-center text-sm">
                  没有找到推理过程类型
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[360px_1fr]">
          <div className="bg-background flex min-h-0 flex-col overflow-hidden rounded-md border">
            <div className="text-muted-foreground flex h-11 flex-shrink-0 items-center justify-between border-b px-3 text-sm">
              <span>{total} 条记录</span>
              <span>
                第 {page} / {totalPages} 页
              </span>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <div className="space-y-1 p-2">
                {items.map((item) => {
                  const active =
                    selected?.stage === item.stage &&
                    selected?.session_id === item.session_id &&
                    selected?.stem === item.stem
                  const durationText = formatDurationMs(item.duration_ms)
                  const metadataText = getReasoningMetadataText(item)
                  return (
                    <button
                      key={`${item.stage}/${item.session_id}/${item.stem}`}
                      type="button"
                      onClick={() => setSelected(item)}
                      className={cn(
                        'flex w-full flex-col gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors',
                        active
                          ? 'border-primary bg-primary/10 text-foreground'
                          : 'hover:border-border hover:bg-muted/60 border-transparent'
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <Badge variant="secondary" className="max-w-[150px] truncate">
                          {formatStageName(item.stage)}
                        </Badge>
                        <span className="text-muted-foreground flex items-center gap-1 text-xs">
                          <Clock className="h-3.5 w-3.5" />
                          {formatTime(item.timestamp, item.modified_at)}
                        </span>
                      </div>
                      {item.stage === 'replyer' && item.output_preview && (
                        <div
                          className="text-foreground line-clamp-2 text-sm"
                          title={item.output_preview}
                        >
                          {item.output_preview}
                        </div>
                      )}
                      {(item.stage === 'planner' || item.stage === 'timing_gate') && item.action_preview && (
                        <div
                          className="text-foreground line-clamp-2 text-sm"
                          title={item.action_preview}
                        >
                          {item.action_preview}
                        </div>
                      )}
                      {metadataText && (
                        <div
                          className="text-muted-foreground flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs"
                          title={metadataText}
                        >
                          {item.model_name && (
                            <span className="inline-flex min-w-0 items-center gap-1">
                              <Cpu className="h-3.5 w-3.5 shrink-0" />
                              <span className="truncate">{item.model_name}</span>
                            </span>
                          )}
                          {durationText && (
                            <span className="inline-flex items-center gap-1">
                              <Timer className="h-3.5 w-3.5 shrink-0" />
                              {durationText}
                            </span>
                          )}
                        </div>
                      )}
                      <div className="text-muted-foreground flex items-center justify-between gap-2 text-xs">
                        <span className="truncate">
                          {item.resolved_session_id
                            ? item.resolved_session_id.slice(0, 8)
                            : item.session_id}{' '}
                          · {item.stem}
                        </span>
                        <span className="shrink-0">{formatSize(item.size)}</span>
                      </div>
                    </button>
                  )
                })}
                {!loading && items.length === 0 && (
                  <div className="text-muted-foreground px-3 py-10 text-center text-sm">
                    没有找到推理过程记录
                  </div>
                )}
              </div>
            </ScrollArea>
            <div className="flex h-12 flex-shrink-0 items-center justify-between border-t px-3">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || loading}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                上一页
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              >
                下一页
              </Button>
            </div>
          </div>

          <div className="bg-background flex min-h-0 flex-col overflow-hidden rounded-md border">
            <div className="flex min-h-14 flex-shrink-0 flex-col gap-1 border-b px-4 py-3 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">
                  {selected
                    ? `${formatStageName(selected.stage)}/${getSessionDisplayName(
                        selected.session_id,
                        selectedSessionInfo,
                        selected.session_display_name
                      )}/${selected.stem}`
                    : '未选择记录'}
                </div>
                <div className="text-muted-foreground text-xs">
                  {selected
                    ? `${formatSize(selected.size)} · ${formatTime(selected.timestamp, selected.modified_at)}`
                    : '从左侧列表选择一条记录'}
                </div>
                {selectedMetadataText && (
                  <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                    {selected?.model_name && (
                      <span className="inline-flex min-w-0 items-center gap-1">
                        <Cpu className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{selected.model_name}</span>
                      </span>
                    )}
                    {selectedDurationText && (
                      <span className="inline-flex items-center gap-1">
                        <Timer className="h-3.5 w-3.5 shrink-0" />
                        {selectedDurationText}
                      </span>
                    )}
                  </div>
                )}
                {selected && selectedSessionInfo && (
                  <div className="text-muted-foreground mt-1 truncate text-xs">
                    {getSessionSubtitle(selectedSessionInfo)}
                  </div>
                )}
              </div>
              {selected && (
                <div className="text-muted-foreground flex items-center gap-2 text-xs">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 gap-1.5"
                    onClick={handleCopyPrompt}
                    disabled={contentLoading || !(textContent || structuredPrompt?.text_dump || jsonContent)}
                    title="复制完整 Prompt"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    复制
                  </Button>
                  {selected.text_path && (
                    <span className="inline-flex items-center gap-1">
                      <FileText className="h-3.5 w-3.5" />
                      txt
                    </span>
                  )}
                  {selected.json_path && (
                    <span className="inline-flex items-center gap-1">
                      <FileJson className="h-3.5 w-3.5" />
                      json
                    </span>
                  )}
                  {selected.html_path && (
                    <span className="inline-flex items-center gap-1">
                      <FileCode2 className="h-3.5 w-3.5" />
                      html
                    </span>
                  )}
                </div>
              )}
            </div>

            <Tabs
              value={activePreview}
              onValueChange={(value) => setActivePreview(value as 'structured' | 'text' | 'html')}
              className="flex min-h-0 flex-1 flex-col"
            >
              <div className="flex flex-shrink-0 border-b px-3 py-2">
                <TabsList>
                  <TabsTrigger value="structured" disabled={!selected?.json_path}>
                    <FileJson className="mr-1 h-4 w-4" />
                    结构化
                  </TabsTrigger>
                  <TabsTrigger value="text" disabled={!selected?.text_path}>
                    <FileText className="mr-1 h-4 w-4" />
                    文本
                  </TabsTrigger>
                  <TabsTrigger value="html" disabled={!selected?.html_path}>
                    <Code2 className="mr-1 h-4 w-4" />
                    HTML
                  </TabsTrigger>
                </TabsList>
              </div>

              <TabsContent value="structured" className="m-0 min-h-0 flex-1 overflow-hidden">
                <ScrollArea className="h-full">
                  {contentLoading ? (
                    <div className="flex min-h-full items-center justify-center p-4">
                      <ThinkingIllustration />
                    </div>
                  ) : structuredPrompt ? (
                    <div className="space-y-3 p-3">
                      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                        <div className="rounded-md border p-3">
                          <div className="text-muted-foreground text-xs">请求类型</div>
                          <div className="mt-1 truncate text-sm font-medium">
                            {structuredPrompt.request?.kind || selected?.stage || '-'}
                          </div>
                        </div>
                        <div className="rounded-md border p-3">
                          <div className="text-muted-foreground text-xs">模型</div>
                          <div className="mt-1 truncate text-sm font-medium">
                            {structuredPrompt.metadata?.model_name || selected?.model_name || '-'}
                          </div>
                        </div>
                        <div className="rounded-md border p-3">
                          <div className="text-muted-foreground text-xs">耗时</div>
                          <div className="mt-1 text-sm font-medium">
                            {formatDurationMs(
                              structuredPrompt.metadata?.duration_ms ?? selected?.duration_ms ?? null
                            ) || '-'}
                          </div>
                        </div>
                        <div className="rounded-md border p-3">
                          <div className="text-muted-foreground text-xs">消息数</div>
                          <div className="mt-1 text-sm font-medium">
                            {structuredPrompt.messages?.length ?? 0}
                          </div>
                        </div>
                      </div>

                      {structuredPrompt.request?.selection_reason && (
                        <div className="rounded-md border p-3">
                          <div className="text-muted-foreground text-xs">选择原因</div>
                          <pre className="text-foreground mt-2 whitespace-pre-wrap break-words text-sm">
                            {structuredPrompt.request.selection_reason}
                          </pre>
                        </div>
                      )}

                      {structuredPrompt.output && (
                        <div className="rounded-md border p-3">
                          <Badge variant="secondary" className="mb-2">
                            {structuredPrompt.output.title || '输出结果'}
                          </Badge>
                          <pre className="text-foreground font-mono text-xs leading-5 whitespace-pre-wrap">
                            {structuredPrompt.output.content_text ||
                              stringifyStructuredValue(structuredPrompt.output.content) ||
                              '空输出'}
                          </pre>
                        </div>
                      )}

                      <div className="space-y-2">
                        {(structuredPrompt.messages ?? []).map((message, index) => (
                          <div key={`${message.index ?? index}-${message.role ?? 'unknown'}`} className="rounded-md border p-3">
                            <div className="mb-2 flex flex-wrap items-center gap-2">
                              <Badge variant="outline">#{message.index ?? index + 1}</Badge>
                              <Badge variant="secondary">{message.role || 'unknown'}</Badge>
                              {message.tool_call_id && (
                                <span className="text-muted-foreground text-xs">
                                  tool_call_id: {message.tool_call_id}
                                </span>
                              )}
                            </div>
                            <pre className="text-foreground font-mono text-xs leading-5 whitespace-pre-wrap">
                              {message.content_text ||
                                stringifyStructuredValue(message.content) ||
                                '空内容'}
                            </pre>
                            {message.tool_calls && message.tool_calls.length > 0 && (
                              <pre className="bg-muted/60 mt-3 rounded-md p-3 font-mono text-xs leading-5 whitespace-pre-wrap">
                                {JSON.stringify(message.tool_calls, null, 2)}
                              </pre>
                            )}
                          </div>
                        ))}
                      </div>

                      {structuredPrompt.tool_definitions && structuredPrompt.tool_definitions.length > 0 && (
                        <div className="rounded-md border p-3">
                          <Badge variant="secondary" className="mb-2">
                            工具定义
                          </Badge>
                          <pre className="text-foreground font-mono text-xs leading-5 whitespace-pre-wrap">
                            {JSON.stringify(structuredPrompt.tool_definitions, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
                      没有结构化内容
                    </div>
                  )}
                </ScrollArea>
              </TabsContent>

              <TabsContent value="text" className="m-0 min-h-0 flex-1 overflow-hidden">
                <ScrollArea className="h-full">
                  {contentLoading ? (
                    <div className="flex min-h-full items-center justify-center p-4">
                      <ThinkingIllustration />
                    </div>
                  ) : (
                    <pre className="text-foreground min-h-full p-4 font-mono text-xs leading-5 break-words whitespace-pre-wrap">
                      {textContent || '没有文本内容'}
                    </pre>
                  )}
                </ScrollArea>
              </TabsContent>

              <TabsContent value="html" className="m-0 min-h-0 flex-1 overflow-hidden">
                {selected?.html_path && htmlPreviewUrl ? (
                  <iframe
                    title="推理过程 HTML 预览"
                    src={htmlPreviewUrl}
                    sandbox=""
                    className="h-full w-full border-0 bg-white"
                  />
                ) : (
                  <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
                    没有 HTML 预览
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </div>
        </div>
      )}
    </div>
  )
}
