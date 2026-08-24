/**
 * PlannerEntry 规划终结条目
 *
 * 推理块 + 工具调用列表（来源标签区分 reasoning/response，不同样式）。
 * token 消耗 + 耗时 + 折叠面板展示详情。
 */
import {
  AlertCircle,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Wrench,
  XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Card, CardHeader, CardTitle } from '@/components/ui/card'
import type { PlannerFinalizedEvent, MaisakaFinalizedToolResult } from '@/lib/maisaka-monitor-client'
import { cn } from '@/lib/utils'

import { formatMs } from './timeline-entry-item'

export interface PlannerEntryProps {
  data: PlannerFinalizedEvent
}

// ─── 辅助函数 ─────────────────────────────────────────────────

function getToolCallSourceLabel(
  source: string | undefined,
  fallbackLabel: string | undefined,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const normalizedSource = (source ?? '').trim().toLowerCase()
  if (normalizedSource === 'reasoning') return t('monitor.maisaka.toolSourceReasoning')
  if (normalizedSource === 'response') return t('monitor.maisaka.toolSourceResponse')
  return fallbackLabel?.trim() || ''
}

function getToolCallSourceBadgeClassName(source: string | undefined): string {
  const normalizedSource = (source ?? '').trim().toLowerCase()
  if (normalizedSource === 'reasoning') {
    return 'border-teal-500/45 bg-teal-500/10 text-teal-700 dark:text-teal-300'
  }
  if (normalizedSource === 'response') {
    return 'border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300'
  }
  return 'border-muted-foreground/30 bg-muted/40 text-muted-foreground'
}

function isPlannerInterrupted(data: PlannerFinalizedEvent): boolean {
  const content = data.planner?.content?.trim() ?? ''
  return data.interrupted === true || (
    content.startsWith('Planner ') &&
    data.planner?.prompt_tokens === 0 &&
    data.planner?.completion_tokens === 0 &&
    (data.planner?.tool_calls.length ?? 0) === 0
  )
}

function formatToolValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === undefined) return 'undefined'
  return JSON.stringify(value, null, 2)
}

function getValueTypeLabel(value: unknown): string {
  if (Array.isArray(value)) return `array(${value.length})`
  if (value === null) return 'null'
  return typeof value
}

// ─── 可折叠文本 ───────────────────────────────────────────────

function CollapsibleText({
  text,
  maxLines = 4,
  className,
  expandLabel,
  collapseLabel,
}: {
  text: string
  maxLines?: number
  className?: string
  expandLabel: string
  collapseLabel: string
}) {
  const [expanded, setExpanded] = useState(false)
  const lines = text.split('\n')
  const needsCollapse = lines.length > maxLines

  if (!needsCollapse || expanded) {
    return (
      <div className="relative">
        <p className={cn('text-sm whitespace-pre-wrap wrap-break-word leading-relaxed', className)}>
          {text}
        </p>
        {needsCollapse && (
          <button
            onClick={() => setExpanded(false)}
            className="text-xs text-primary hover:underline mt-1 flex items-center gap-0.5"
          >
            <ChevronDown className="h-3 w-3" /> {collapseLabel}
          </button>
        )}
      </div>
    )
  }

  return (
    <div>
      <p className={cn('text-sm whitespace-pre-wrap wrap-break-word leading-relaxed', className)}>
        {lines.slice(0, maxLines).join('\n')}
      </p>
      <button
        onClick={() => setExpanded(true)}
        className="text-xs text-primary hover:underline mt-1 flex items-center gap-0.5"
      >
        <ChevronRight className="h-3 w-3" /> {expandLabel} ({lines.length})
      </button>
    </div>
  )
}

// ─── 工具参数块 ───────────────────────────────────────────────

function ToolArgumentBlock({ name, value }: { name: string; value: unknown }) {
  const formattedValue = formatToolValue(value)
  const inlineValue = formattedValue.replace(/\s+/g, ' ')

  return (
    <div
      className="flex h-6 max-w-full min-w-0 items-center gap-1.5 rounded-md border bg-background/60 px-2 text-xs"
      title={`${name} (${getValueTypeLabel(value)}): ${formattedValue}`}
    >
      <span className="shrink-0 font-mono font-semibold text-foreground">{name}</span>
      <span className="shrink-0 text-muted-foreground">=</span>
      <span className="min-w-0 max-w-72 truncate font-mono text-[11px] text-muted-foreground">
        {inlineValue}
      </span>
    </div>
  )
}

function ToolFullJsonBlock({ tool }: { tool: MaisakaFinalizedToolResult }) {
  const [open, setOpen] = useState(false)
  const payload = {
    tool_call_id: tool.tool_call_id,
    tool_name: tool.tool_name,
    tool_args: tool.tool_args,
    success: tool.success,
    duration_ms: tool.duration_ms,
    summary: tool.summary,
    prompt_html_uri: tool.prompt_html_uri,
    tool_call_source: tool.tool_call_source,
    tool_call_source_label: tool.tool_call_source_label,
  }

  return (
    <div className="contents text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="ml-auto flex h-6 cursor-pointer items-center gap-1 rounded border border-dashed bg-background/40 px-1.5 text-[10px] text-muted-foreground hover:bg-muted/40"
        title="JSON"
      >
        <ChevronRight className={cn('h-2.5 w-2.5 shrink-0 transition-transform', open && 'rotate-90')} />
        <span>JSON</span>
      </button>
      {open && (
        <pre className="basis-full rounded-md border bg-background/60 px-2.5 py-1.5 font-mono text-[11px] leading-4 whitespace-pre-wrap break-words text-muted-foreground">
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </div>
  )
}

// ─── 工具结果卡片 ─────────────────────────────────────────────

function PlannerToolResultCard({
  tool,
  index,
  showDivider,
}: {
  tool: MaisakaFinalizedToolResult
  index: number
  showDivider: boolean
}) {
  const { t } = useTranslation()
  const argumentEntries = Object.entries(tool.tool_args ?? {})
  const statusText = tool.success ? t('monitor.maisaka.toolSuccess') : t('monitor.maisaka.toolFailed')
  const sourceLabel = getToolCallSourceLabel(tool.tool_call_source, tool.tool_call_source_label, t)

  return (
    <div className="space-y-2">
      {showDivider && <div className="border-b border-border" />}
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-sm font-semibold text-foreground">{tool.tool_name || 'unknown'}</span>
          {tool.success
            ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            : <XCircle className="h-3.5 w-3.5 text-red-500" />
          }
          <Badge variant={tool.success ? 'secondary' : 'destructive'} className="h-5 px-1.5 text-[10px]">
            {statusText}
          </Badge>
          {sourceLabel && (
            <Badge
              variant="outline"
              className={cn('h-5 px-1.5 text-[10px]', getToolCallSourceBadgeClassName(tool.tool_call_source))}
            >
              {sourceLabel}
            </Badge>
          )}
          {tool.duration_ms > 0 && (
            <span className="text-xs font-medium text-muted-foreground">{formatMs(tool.duration_ms)}</span>
          )}
          <span className="ml-auto text-[10px] text-muted-foreground">#{index + 1}</span>
        </div>

        <div className="space-y-1.5">
          {argumentEntries.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {argumentEntries.map(([name, value]) => (
                <ToolArgumentBlock key={name} name={name} value={value} />
              ))}
              <ToolFullJsonBlock tool={tool} />
            </div>
          )}

          <div className="flex items-start gap-1.5 rounded-md border bg-muted/20 px-2.5 py-1">
            <span className="shrink-0 text-[10px] font-medium leading-4 text-muted-foreground">
              {t('monitor.maisaka.toolResult')}
            </span>
            <p className="min-w-0 flex-1 text-xs leading-4 whitespace-pre-wrap break-words text-foreground/80">
              {tool.summary || t('monitor.maisaka.toolNoSummary')}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── 工具调用块 ───────────────────────────────────────────────

function PlannerToolCallsBlock({ data }: { data: PlannerFinalizedEvent }) {
  const { t } = useTranslation()
  const toolCalls = data.planner?.tool_calls ?? []
  const tools = data.tools ?? []
  const displayTools: MaisakaFinalizedToolResult[] = tools.length > 0
    ? tools
    : toolCalls.map((toolCall) => ({
        tool_call_id: toolCall.id,
        tool_name: toolCall.name,
        tool_args: toolCall.arguments ?? {},
        tool_call_source: toolCall.source,
        tool_call_source_label: toolCall.source_label,
        success: true,
        duration_ms: 0,
        summary: '',
      }))
  const isFinishTool = (toolName: string | undefined) => toolName?.trim().toLowerCase() === 'finish'
  const finishTools = displayTools.filter((tool) => isFinishTool(tool.tool_name))
  const regularTools = displayTools.filter((tool) => !isFinishTool(tool.tool_name))

  if (displayTools.length <= 0) {
    return null
  }

  if (regularTools.length <= 0 && finishTools.length > 0) {
    return (
      <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2">
        <div className="flex items-center gap-2 text-sm">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
          <span className="font-medium">{t('monitor.maisaka.cycleFinished')}</span>
          <span className="text-muted-foreground">{t('monitor.maisaka.waitingNewMessage')}</span>
        </div>
      </div>
    )
  }

  return (
    <Card className="border-l-4 border-l-teal-500/60">
      <CardHeader className="py-3 px-4 space-y-2">
        <div className="flex items-center gap-2">
          <Wrench className="h-4 w-4 text-teal-500" />
          <CardTitle className="text-sm font-medium">{t('monitor.maisaka.toolCalls')}</CardTitle>
          <Badge variant="secondary" className="ml-auto text-[10px]">
            {t('monitor.maisaka.toolCount', { count: regularTools.length })}
          </Badge>
        </div>
        {finishTools.length > 0 && (
          <div className="flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/5 px-2.5 py-1.5 text-xs">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
            <span className="font-medium">{t('monitor.maisaka.cycleFinished')}</span>
            <span className="text-muted-foreground">{t('monitor.maisaka.waitingNewMessage')}</span>
          </div>
        )}
        <div className="space-y-2">
          {regularTools.map((tool, idx) => (
            <PlannerToolResultCard
              key={`${tool.tool_call_id || tool.tool_name}-${idx}`}
              tool={tool}
              index={idx}
              showDivider={idx > 0}
            />
          ))}
        </div>
      </CardHeader>
    </Card>
  )
}

// ─── Planner 被打断 ───────────────────────────────────────────

function PlannerInterruptedCard({ data }: { data: PlannerFinalizedEvent }) {
  const { t } = useTranslation()
  const planner = data.planner

  return (
    <div className="rounded-md border border-amber-500/35 bg-amber-500/5 px-3 py-2">
      <div className="flex items-center gap-2 text-sm">
        <AlertCircle className="h-4 w-4 shrink-0 text-amber-500" />
        <span className="font-medium">{t('monitor.maisaka.plannerInterrupted')}</span>
        <Badge variant="outline" className="ml-auto text-[10px]">
          #{data.cycle_id}
        </Badge>
        {planner && planner.duration_ms > 0 && (
          <span className="text-xs text-muted-foreground">{formatMs(planner.duration_ms)}</span>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        {planner?.content || t('monitor.maisaka.plannerInterruptedHint')}
      </p>
    </div>
  )
}

// ─── Planner 推理块 ───────────────────────────────────────────

function PlannerFinalizedCard({ data }: { data: PlannerFinalizedEvent }) {
  const { t } = useTranslation()
  const planner = data.planner

  return (
    <Card className="border-l-4 border-l-emerald-500/60">
      <CardHeader className="py-3 px-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Brain className="h-4 w-4 text-emerald-500" />
          <CardTitle className="text-sm font-medium">Planner</CardTitle>
          <Badge variant="outline" className="text-xs font-normal ml-auto">
            {formatMs(planner?.duration_ms ?? 0)}
          </Badge>
          {data.request && (
            <Badge variant="secondary" className="text-[10px]">
              {t('monitor.maisaka.contextSummary', {
                history: data.request.selected_history_count,
                tools: data.request.tool_count,
              })}
            </Badge>
          )}
          {planner && (planner.prompt_tokens > 0 || planner.completion_tokens > 0) && (
            <Badge variant="outline" className="text-[10px]">
              {t('monitor.maisaka.tokenUsage', {
                prompt: planner.prompt_tokens,
                completion: planner.completion_tokens,
              })}
            </Badge>
          )}
        </div>

        {planner?.content ? (
          <CollapsibleText
            text={planner.content}
            maxLines={6}
            className="text-foreground/90"
            expandLabel={t('monitor.maisaka.expandAll')}
            collapseLabel={t('monitor.maisaka.collapse')}
          />
        ) : (
          <p className="text-sm text-muted-foreground">{t('monitor.maisaka.plannerNoContent')}</p>
        )}
      </CardHeader>
    </Card>
  )
}

// ─── 主组件 ───────────────────────────────────────────────────

export function PlannerEntry({ data }: PlannerEntryProps) {
  if (isPlannerInterrupted(data)) {
    return <PlannerInterruptedCard data={data} />
  }

  return (
    <div className="space-y-2">
      <PlannerFinalizedCard data={data} />
      <PlannerToolCallsBlock data={data} />
    </div>
  )
}