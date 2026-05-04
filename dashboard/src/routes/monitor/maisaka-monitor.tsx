/**
 * MaiSaka 聊天流实时监控组件
 *
 * 通过 WebSocket 实时接收 MaiSaka 推理引擎事件，
 * 以时间线形式展示聊天流的推理过程。
 */
import {
  Activity,
  ArrowRight,
  Bot,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Clock,
  Eraser,
  Gauge,
  MessageSquare,
  PauseCircle,
  Timer,
  Wrench,
  XCircle,
  Zap,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { useCallback, useEffect, useRef, useState } from 'react'

import type {
  CycleEndEvent,
  CycleStartEvent,
  MaisakaToolCall,
  MessageIngestedEvent,
  PlannerResponseEvent,
  ReplierResponseEvent,
  TimingGateResultEvent,
  ToolExecutionEvent,
} from '@/lib/maisaka-monitor-client'
import type { SessionInfo, TimelineEntry } from './use-maisaka-monitor'
import { useMaisakaMonitor } from './use-maisaka-monitor'

// ─── 工具函数 ──────────────────────────────────────────────────

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatRelativeTime(ts: number): string {
  const diff = Date.now() / 1000 - ts
  if (diff < 10) return '刚刚'
  if (diff < 60) return `${Math.round(diff)}秒前`
  if (diff < 3600) return `${Math.round(diff / 60)}分钟前`
  return `${Math.round(diff / 3600)}小时前`
}

// ─── 会话侧边栏 ──────────────────────────────────────────────

function SessionSidebar({
  sessions,
  selectedSession,
  onSelect,
}: {
  sessions: Map<string, SessionInfo>
  selectedSession: string | null
  onSelect: (id: string) => void
}) {
  const sortedSessions = Array.from(sessions.values()).sort(
    (a, b) => b.lastActivity - a.lastActivity,
  )

  if (sortedSessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2 p-4">
        <Bot className="h-8 w-8 opacity-40" />
        <p className="text-sm text-center">等待 MaiSaka 会话…</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1 p-2">
      {sortedSessions.map((session) => (
        <button
          key={session.sessionId}
          onClick={() => onSelect(session.sessionId)}
          className={cn(
            'flex flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left text-sm transition-colors',
            'hover:bg-accent/50',
            selectedSession === session.sessionId && 'bg-accent text-accent-foreground',
          )}
        >
          <div className="flex w-full items-center justify-between">
            <div className="flex min-w-0 items-center gap-1.5">
              {session.isGroupChat !== undefined && (
                <Badge variant="outline" className="h-4 shrink-0 px-1 text-[10px]">
                  {session.isGroupChat ? '群' : '私'}
                </Badge>
              )}
              <span className="truncate font-medium" title={session.sessionName}>
                {session.sessionName}
              </span>
            </div>
            <Badge variant="secondary" className="h-4 shrink-0 px-1 text-[10px]">
              {session.eventCount}
            </Badge>
          </div>
          <span className="text-xs text-muted-foreground">
            {formatRelativeTime(session.lastActivity)}
          </span>
        </button>
      ))}
    </div>
  )
}

// ─── 单条时间线事件渲染 ──────────────────────────────────────

function MessageIngestedCard({ data }: { data: MessageIngestedEvent }) {
  return (
    <div className="flex items-start gap-3">
      <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-500/15 text-blue-500">
        <MessageSquare className="h-3.5 w-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-sm">{data.speaker_name}</span>
          <span className="text-xs text-muted-foreground">{formatTimestamp(data.timestamp)}</span>
        </div>
        <p className="text-sm text-foreground/80 whitespace-pre-wrap wrap-break-word leading-relaxed">
          {data.content || '[空消息]'}
        </p>
      </div>
    </div>
  )
}

function CycleStartCard({ data }: { data: CycleStartEvent }) {
  return (
    <div className="flex items-center gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-violet-500/15 text-violet-500">
        <Zap className="h-3.5 w-3.5" />
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-medium">推理循环 #{data.cycle_id}</span>
        <Badge variant="outline" className="text-[10px]">
          回合 {data.round_index + 1}/{data.max_rounds}
        </Badge>
        <Badge variant="secondary" className="text-[10px]">
          上下文 {data.history_count} 条
        </Badge>
      </div>
    </div>
  )
}

function TimingGateCard({ data }: { data: TimingGateResultEvent }) {
  const actionConfig: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive'; icon: typeof ArrowRight }> = {
    continue: { label: '继续执行', variant: 'default', icon: ArrowRight },
    wait: { label: '等待', variant: 'secondary', icon: PauseCircle },
    no_reply: { label: '不回复', variant: 'destructive', icon: XCircle },
  }
  const config = actionConfig[data.action] ?? actionConfig.continue
  const Icon = config.icon

  return (
    <div className="flex items-start gap-3">
      <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-amber-500">
        <Timer className="h-3.5 w-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span className="text-sm font-medium">Timing Gate</span>
          <Badge variant={config.variant} className="text-[10px] gap-0.5">
            <Icon className="h-2.5 w-2.5" />
            {config.label}
          </Badge>
          <span className="text-xs text-muted-foreground">{formatMs(data.duration_ms)}</span>
        </div>
        {data.content && (
          <CollapsibleText text={data.content} maxLines={3} />
        )}
      </div>
    </div>
  )
}

function PlannerResponseCard({ data }: { data: PlannerResponseEvent }) {
  return (
    <div className="flex items-start gap-3">
      <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-500">
        <Brain className="h-3.5 w-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span className="text-sm font-medium">规划器思考</span>
          <span className="text-xs text-muted-foreground">{formatMs(data.duration_ms)}</span>
          <Badge variant="outline" className="text-[10px]">
            {data.prompt_tokens}+{data.completion_tokens} tokens
          </Badge>
        </div>
        {data.content && (
          <CollapsibleText text={data.content} maxLines={6} />
        )}
        {data.tool_calls.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {data.tool_calls.map((tc: MaisakaToolCall, idx: number) => (
              <Badge key={idx} variant="secondary" className="text-[10px] gap-1">
                <Wrench className="h-2.5 w-2.5" />
                {tc.name}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ToolExecutionCard({ data }: { data: ToolExecutionEvent }) {
  return (
    <div className="flex items-start gap-3">
      <div className={cn(
        'mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full',
        data.success
          ? 'bg-teal-500/15 text-teal-500'
          : 'bg-red-500/15 text-red-500',
      )}>
        <Wrench className="h-3.5 w-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span className="text-sm font-medium font-mono">{data.tool_name}</span>
          {data.success
            ? <CheckCircle2 className="h-3.5 w-3.5 text-teal-500" />
            : <XCircle className="h-3.5 w-3.5 text-red-500" />
          }
          <span className="text-xs text-muted-foreground">{formatMs(data.duration_ms)}</span>
        </div>
        {Object.keys(data.tool_args).length > 0 && (
          <div className="text-xs text-muted-foreground font-mono bg-muted/50 rounded px-2 py-1 mb-1 whitespace-pre-wrap break-all">
            {JSON.stringify(data.tool_args, null, 2)}
          </div>
        )}
        {data.result_summary && (
          <CollapsibleText text={data.result_summary} maxLines={3} className="text-muted-foreground" />
        )}
      </div>
    </div>
  )
}

function CycleEndCard({ data }: { data: CycleEndEvent }) {
  const totalTime = Object.values(data.time_records).reduce((a, b) => a + b, 0)
  return (
    <div className="flex items-center gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-500/15 text-slate-500">
        <CircleDot className="h-3.5 w-3.5" />
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-muted-foreground">循环结束</span>
        <Badge variant="outline" className="text-[10px]">
          总耗时 {formatMs(totalTime * 1000)}
        </Badge>
        {Object.entries(data.time_records).map(([name, duration]) => (
          <span key={name} className="text-[10px] text-muted-foreground">
            {name}: {formatMs(duration * 1000)}
          </span>
        ))}
        <Badge
          variant={data.agent_state === 'running' ? 'default' : 'secondary'}
          className="text-[10px]"
        >
          {data.agent_state}
        </Badge>
      </div>
    </div>
  )
}

// ─── 可折叠文本组件 ────────────────────────────────────────────

function CollapsibleText({
  text,
  maxLines = 4,
  className,
}: {
  text: string
  maxLines?: number
  className?: string
}) {
  const [expanded, setExpanded] = useState(false)
  const lines = text.split('\n')
  const needsCollapse = lines.length > maxLines

  if (!needsCollapse || expanded) {
    return (
      <div className="relative">
        <p className={cn(
          'text-sm whitespace-pre-wrap wrap-break-word leading-relaxed',
          className,
        )}>
          {text}
        </p>
        {needsCollapse && (
          <button
            onClick={() => setExpanded(false)}
            className="text-xs text-primary hover:underline mt-1 flex items-center gap-0.5"
          >
            <ChevronDown className="h-3 w-3" /> 收起
          </button>
        )}
      </div>
    )
  }

  return (
    <div>
      <p className={cn(
        'text-sm whitespace-pre-wrap wrap-break-word leading-relaxed',
        className,
      )}>
        {lines.slice(0, maxLines).join('\n')}
      </p>
      <button
        onClick={() => setExpanded(true)}
        className="text-xs text-primary hover:underline mt-1 flex items-center gap-0.5"
      >
        <ChevronRight className="h-3 w-3" /> 展开全部 ({lines.length} 行)
      </button>
    </div>
  )
}

// ─── 回复器响应卡片 ──────────────────────────────────────────

function ReplierResponseCard({ data }: { data: ReplierResponseEvent }) {
  return (
    <Card className="border-l-4 border-l-purple-500/60">
      <CardHeader className="py-2.5 px-4 space-y-2">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-purple-500" />
          <CardTitle className="text-sm font-medium">回复器响应</CardTitle>
          <Badge variant="outline" className="text-xs font-normal ml-auto">
            {formatMs(data.duration_ms)}
          </Badge>
          {data.success ? (
            <Badge variant="secondary" className="text-xs gap-1">
              <CheckCircle2 className="h-3 w-3" /> 成功
            </Badge>
          ) : (
            <Badge variant="destructive" className="text-xs gap-1">
              <XCircle className="h-3 w-3" /> 失败
            </Badge>
          )}
          <span className="text-xs text-muted-foreground">{formatTimestamp(data.timestamp)}</span>
        </div>
        {data.content && (
          <CollapsibleText text={data.content} maxLines={6} className="text-foreground/90" />
        )}
        {data.reasoning && (
          <details className="mt-1">
            <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
              思考过程
            </summary>
            <CollapsibleText text={data.reasoning} maxLines={8} className="mt-1 text-muted-foreground" />
          </details>
        )}
        {(data.prompt_tokens > 0 || data.completion_tokens > 0) && (
          <div className="flex gap-3 text-xs text-muted-foreground mt-1">
            {data.model_name && <span>模型: {data.model_name}</span>}
            <span>输入: {data.prompt_tokens}</span>
            <span>输出: {data.completion_tokens}</span>
            <span>总计: {data.total_tokens}</span>
          </div>
        )}
      </CardHeader>
    </Card>
  )
}

// ─── 时间线入口渲染器 ──────────────────────────────────────────

function TimelineEventRenderer({ entry }: { entry: TimelineEntry }) {
  switch (entry.type) {
    case 'message.ingested':
      return <MessageIngestedCard data={entry.data as MessageIngestedEvent} />
    case 'cycle.start':
      return <CycleStartCard data={entry.data as CycleStartEvent} />
    case 'timing_gate.result':
      return <TimingGateCard data={entry.data as TimingGateResultEvent} />
    case 'planner.response':
      return <PlannerResponseCard data={entry.data as PlannerResponseEvent} />
    case 'tool.execution':
      return <ToolExecutionCard data={entry.data as ToolExecutionEvent} />
    case 'cycle.end':
      return <CycleEndCard data={entry.data as CycleEndEvent} />
    case 'replier.response':
      return <ReplierResponseCard data={entry.data as ReplierResponseEvent} />
    // planner.request, replier.request 和 session.start 通常不需要在 timeline 中主要展示
    default:
      return null
  }
}

// ─── 主组件 ─────────────────────────────────────────────────

export function MaisakaMonitor() {
  const {
    timeline,
    sessions,
    selectedSession,
    setSelectedSession,
    connected,
    clearTimeline,
  } = useMaisakaMonitor()

  const scrollRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  // 自动滚动到底部
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      const viewport = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]')
      if (viewport) {
        viewport.scrollTop = viewport.scrollHeight
      }
    }
  }, [timeline, autoScroll])

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget.querySelector('[data-radix-scroll-area-viewport]')
    if (!target) return
    const { scrollTop, scrollHeight, clientHeight } = target as HTMLElement
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 80)
  }, [])

  // 统计当前会话的各事件类型计数
  const stats = {
    messages: timeline.filter((e) => e.type === 'message.ingested').length,
    cycles: timeline.filter((e) => e.type === 'cycle.start').length,
    toolCalls: timeline.filter((e) => e.type === 'tool.execution').length,
  }

  return (
    <div className="flex h-[calc(100vh-180px)] gap-4">
      {/* 会话侧边栏 */}
      <Card className="w-60 shrink-0 flex flex-col">
        <CardHeader className="py-3 px-4 space-y-0">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Activity className="h-4 w-4" />
            聊天流
            {connected && (
              <span className="ml-auto flex h-2 w-2 rounded-full bg-emerald-500" />
            )}
          </CardTitle>
        </CardHeader>
        <Separator />
        <ScrollArea className="flex-1">
          <SessionSidebar
            sessions={sessions}
            selectedSession={selectedSession}
            onSelect={setSelectedSession}
          />
        </ScrollArea>
      </Card>

      {/* 主时间线区域 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 顶部统计栏 */}
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <MessageSquare className="h-3.5 w-3.5" />
              <span>{stats.messages} 消息</span>
            </div>
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Brain className="h-3.5 w-3.5" />
              <span>{stats.cycles} 循环</span>
            </div>
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Wrench className="h-3.5 w-3.5" />
              <span>{stats.toolCalls} 工具调用</span>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => setAutoScroll(!autoScroll)}
            >
              <Gauge className={cn('h-3.5 w-3.5 mr-1', autoScroll && 'text-primary')} />
              {autoScroll ? '跟踪中' : '已暂停'}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={clearTimeline}
            >
              <Eraser className="h-3.5 w-3.5 mr-1" />
              清空
            </Button>
          </div>
        </div>

        {/* 时间线 */}
        <Card className="flex-1 overflow-hidden">
          <ScrollArea
            className="h-full"
            ref={scrollRef}
            onScrollCapture={handleScroll}
          >
            <div className="p-4 space-y-3">
              {timeline.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-muted-foreground gap-3">
                  <Clock className="h-10 w-10 opacity-30" />
                  <p className="text-sm">等待 MaiSaka 推理事件…</p>
                  <p className="text-xs opacity-60">
                    当 MaiSaka 处理新消息时，推理过程会实时展示在这里
                  </p>
                </div>
              ) : (
                timeline.map((entry) => {
                  const rendered = <TimelineEventRenderer entry={entry} />
                  if (!rendered) return null
                  return (
                    <div
                      key={entry.id}
                      className="animate-in fade-in-0 slide-in-from-bottom-2 duration-300"
                    >
                      {rendered}
                      {entry.type === 'cycle.end' && (
                        <Separator className="mt-3" />
                      )}
                    </div>
                  )
                })
              )}
            </div>
          </ScrollArea>
        </Card>
      </div>
    </div>
  )
}
