/**
 * TalkFrequencyTimelineRule 时间轴编辑器（R3-2-2）
 *
 * 从 dashboard routes/chat-management.tsx 523-1065 行搬移。
 * 包含：FrequencySummaryItem / RuleStackItem / RuleEditor / TimelineRule / TimelineEditor / Editor / Section
 *
 * 适配点：
 * - useToast → sonner toast()
 * - data-dashboard-slider → showValue + valueFormat props
 * - getChatTypeText 从 chat-management-utils 导入
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import type { PointerEvent } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import {
  deleteChatStreamTalkFrequency,
  updateChatStreamTalkFrequency,
  type ChatStreamDetail,
  type ChatTalkFrequencyRule,
} from '@/lib/chat-management-api'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

import { getChatTypeText } from '../chat-management-utils'
import {
  clampTalkFrequencyValue,
  DAY_MINUTES,
  formatFrequencySummary,
  formatTimelineMinute,
  formatTalkTimeRange,
  getExactTalkRules,
  getTimelineMinuteFromClient,
  getTimelineSegments,
  parseTalkTimeRange,
  talkValueColor,
  TIMELINE_TICKS,
  type TalkFrequencyEditMode,
  type TimelineEdge,
} from './talk-frequency-utils'

/** 状态徽章 */
function StatusBadge({ enabled }: { enabled: boolean }) {
  return (
    <Badge variant={enabled ? 'default' : 'secondary'}>
      {enabled ? '已启用' : '已禁用'}
    </Badge>
  )
}

/** 频率摘要项 */
function FrequencySummaryItem({
  formatValue = true,
  label,
  value,
}: {
  formatValue?: boolean
  label: string
  value: string
}) {
  return (
    <div className="min-w-0 space-y-1 text-sm">
      <div className="text-muted-foreground">{label}</div>
      <div className="font-mono font-semibold whitespace-nowrap tabular-nums">
        {formatValue ? formatFrequencySummary(value) : value}
      </div>
    </div>
  )
}

/** 规则栈项（展示已匹配规则） */
function TalkFrequencyRuleStackItem({ rule }: { rule: ChatTalkFrequencyRule }) {
  const targetLabel = `${rule.platform || '*'}:${rule.item_id || '*'}:${rule.type || '-'}`
  const timeLabel = rule.time || '默认'
  const timePriority = rule.time_priority ?? 0

  return (
    <div
      className={cn(
        'rounded-md border px-3 py-2 text-sm',
        rule.is_effective
          ? 'border-primary bg-primary/10 text-foreground'
          : 'bg-muted text-muted-foreground'
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {rule.is_effective && <Badge variant="default">生效中</Badge>}
        {!rule.is_effective && !rule.time_active && <Badge variant="outline">时间未命中</Badge>}
        <span className="font-mono text-xs">{targetLabel}</span>
        <span className="text-xs">
          优先级 {rule.target_priority}.{timePriority}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
        <span>时间：{timeLabel}</span>
        <span>频率：{formatFrequencySummary(rule.value_label)}</span>
      </div>
    </div>
  )
}

/** 普通输入模式规则编辑器 */
function TalkFrequencyRuleEditor({
  detail,
  rule,
}: {
  detail: ChatStreamDetail
  rule?: ChatTalkFrequencyRule
}) {
  const queryClient = useQueryClient()
  const isNewRule = !rule
  const [time, setTime] = useState(rule?.time ?? '*')
  const [value, setValue] = useState(() =>
    clampTalkFrequencyValue(rule?.value ?? detail.talk_frequency.effective_value)
  )

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      setTime(rule?.time ?? '*')
      setValue(clampTalkFrequencyValue(rule?.value ?? detail.talk_frequency.effective_value))
    })

    return () => window.cancelAnimationFrame(frameId)
  }, [detail.session_id, detail.talk_frequency.effective_value, rule])

  const updateDetailCache = (updatedDetail: ChatStreamDetail) => {
    queryClient.setQueryData(['chat-stream-detail', detail.session_id], updatedDetail)
    void queryClient.invalidateQueries({ queryKey: ['chat-streams'] })
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      updateChatStreamTalkFrequency(detail.session_id, {
        previous_time: rule?.time ?? null,
        time: time.trim(),
        value: clampTalkFrequencyValue(value),
      }),
    onSuccess: (updatedDetail) => {
      updateDetailCache(updatedDetail)
      toast.success(isNewRule ? '发言频率规则已新增' : '发言频率规则已保存', {
        description: '已写入当前聊天流的精确动态频率规则。',
      })
    },
    onError: (error) => {
      toast.error('保存发言频率失败', {
        description: error instanceof Error ? error.message : '请稍后重试',
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteChatStreamTalkFrequency(detail.session_id, rule?.time ?? ''),
    onSuccess: (updatedDetail) => {
      updateDetailCache(updatedDetail)
      toast.success('发言频率规则已删除', {
        description: '已删除当前聊天流的这条精确规则。',
      })
    },
    onError: (error) => {
      toast.error('删除发言频率规则失败', {
        description: error instanceof Error ? error.message : '请稍后重试',
      })
    },
  })

  return (
    <div className="bg-muted/25 grid gap-3 rounded-md border p-3 sm:grid-cols-[minmax(8rem,12rem)_1fr_auto] sm:items-end">
      <div className="space-y-2">
        <Label className="text-xs">{isNewRule ? '新增时间段' : '时间段'}</Label>
        <Input
          value={time}
          placeholder="* 或 HH:MM-HH:MM"
          onChange={(event) => setTime(event.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label className="text-xs">发言频率</Label>
        <Input
          type="number"
          min={0}
          max={1}
          step={0.01}
          value={value}
          onChange={(event) => setValue(clampTalkFrequencyValue(Number(event.target.value)))}
        />
      </div>
      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          className="shrink-0"
          disabled={saveMutation.isPending}
          onClick={() => saveMutation.mutate()}
        >
          {saveMutation.isPending ? '保存中...' : isNewRule ? '新增' : '保存'}
        </Button>
        {!isNewRule && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="text-destructive hover:text-destructive shrink-0"
            disabled={deleteMutation.isPending}
            aria-label={`删除时间段 ${rule.time || '默认'} 的发言频率规则`}
            onClick={() => deleteMutation.mutate()}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  )
}

/** 时间轴模式规则编辑器（24h 拖拽起止 + Slider 0-1） */
function TalkFrequencyTimelineRule({
  detail,
  rule,
}: {
  detail: ChatStreamDetail
  rule?: ChatTalkFrequencyRule
}) {
  const queryClient = useQueryClient()
  const isNewRule = !rule
  const [time, setTime] = useState(rule?.time || '00:00-23:59')
  const [value, setValue] = useState(() =>
    clampTalkFrequencyValue(rule?.value ?? detail.talk_frequency.effective_value)
  )
  const draggingEdgeRef = useRef<TimelineEdge | null>(null)
  const range = parseTalkTimeRange(time)
  const draggableRange = range && time.trim() !== '' && time.trim() !== '*'
  const segments = range ? getTimelineSegments(range) : []
  const startLabelLeft = range ? (range.start / DAY_MINUTES) * 100 : 0
  const endLabelLeft = range ? ((range.end + 1) / DAY_MINUTES) * 100 : 100
  const startLabelTransform = startLabelLeft < 4 ? 'translateX(0)' : 'translateX(-50%)'
  const endLabelTransform = endLabelLeft > 96 ? 'translateX(-100%)' : 'translateX(-50%)'

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      setTime(rule?.time || '00:00-23:59')
      setValue(clampTalkFrequencyValue(rule?.value ?? detail.talk_frequency.effective_value))
    })

    return () => window.cancelAnimationFrame(frameId)
  }, [detail.session_id, detail.talk_frequency.effective_value, rule])

  const updateDetailCache = (updatedDetail: ChatStreamDetail) => {
    queryClient.setQueryData(['chat-stream-detail', detail.session_id], updatedDetail)
    void queryClient.invalidateQueries({ queryKey: ['chat-streams'] })
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      updateChatStreamTalkFrequency(detail.session_id, {
        previous_time: rule?.time ?? null,
        time: time.trim(),
        value: clampTalkFrequencyValue(value),
      }),
    onSuccess: (updatedDetail) => {
      updateDetailCache(updatedDetail)
      toast.success(isNewRule ? '发言频率规则已新增' : '发言频率规则已保存', {
        description: '已写入当前聊天流的精确动态频率规则。',
      })
    },
    onError: (error) => {
      toast.error('保存发言频率失败', {
        description: error instanceof Error ? error.message : '请稍后重试',
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteChatStreamTalkFrequency(detail.session_id, rule?.time ?? ''),
    onSuccess: (updatedDetail) => {
      updateDetailCache(updatedDetail)
      toast.success('发言频率规则已删除', {
        description: '已删除当前聊天流的这条精确规则。',
      })
    },
    onError: (error) => {
      toast.error('删除发言频率规则失败', {
        description: error instanceof Error ? error.message : '请稍后重试',
      })
    },
  })

  const updateTimeFromPointer = (event: PointerEvent<HTMLElement>, edge: TimelineEdge) => {
    if (!range) {
      return
    }
    const timelineElement = event.currentTarget.closest('[data-chat-talk-timeline-track]')
    if (!(timelineElement instanceof HTMLElement)) {
      return
    }
    const nextMinute = getTimelineMinuteFromClient(event.clientX, timelineElement)
    const nextRange =
      edge === 'start' ? { ...range, start: nextMinute } : { ...range, end: nextMinute }
    setTime(formatTalkTimeRange(nextRange))
  }

  const startDrag = (event: PointerEvent<HTMLElement>, edge: TimelineEdge) => {
    event.preventDefault()
    draggingEdgeRef.current = edge
    event.currentTarget.setPointerCapture(event.pointerId)
    updateTimeFromPointer(event, edge)
  }

  return (
    <div className="bg-muted/25 grid min-w-0 gap-3 rounded-md border p-3 xl:grid-cols-[minmax(12rem,1fr)_8rem_8rem] xl:items-center">
      <div className="min-w-0">
        <div className="text-muted-foreground relative mb-1 h-4 px-1 text-[10px]">
          {TIMELINE_TICKS.map((hour) => (
            <span
              key={hour}
              className="absolute -translate-x-1/2"
              style={{ left: `${(hour / 24) * 100}%` }}
            >
              {hour.toString().padStart(2, '0')}
            </span>
          ))}
        </div>
        <div className="bg-background relative h-8 rounded-md border" data-chat-talk-timeline-track>
          {TIMELINE_TICKS.slice(1, -1).map((hour) => (
            <span
              key={hour}
              className="border-muted-foreground/20 absolute top-0 h-full border-l border-dashed"
              style={{ left: `${(hour / 24) * 100}%` }}
            />
          ))}
          {segments.map((segment, index) => (
            <span
              key={index}
              className={cn(
                'absolute top-1/2 h-4 -translate-y-1/2 rounded-sm opacity-85',
                talkValueColor(value),
                !range && 'opacity-35'
              )}
              style={{ left: `${segment.left}%`, width: `${segment.width}%` }}
            />
          ))}
          {draggableRange && (
            <>
              <button
                type="button"
                className="border-background bg-foreground/80 absolute top-1/2 h-7 w-2 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize rounded-sm border"
                style={{ left: `${(range.start / DAY_MINUTES) * 100}%` }}
                aria-label="调整开始时间"
                onPointerDown={(event) => startDrag(event, 'start')}
                onPointerMove={(event) => {
                  if (
                    draggingEdgeRef.current === 'start' &&
                    event.currentTarget.hasPointerCapture(event.pointerId)
                  ) {
                    updateTimeFromPointer(event, 'start')
                  }
                }}
                onPointerUp={(event) => {
                  draggingEdgeRef.current = null
                  event.currentTarget.releasePointerCapture(event.pointerId)
                }}
              />
              <button
                type="button"
                className="border-background bg-foreground/80 absolute top-1/2 h-7 w-2 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize rounded-sm border"
                style={{ left: `${((range.end + 1) / DAY_MINUTES) * 100}%` }}
                aria-label="调整结束时间"
                onPointerDown={(event) => startDrag(event, 'end')}
                onPointerMove={(event) => {
                  if (
                    draggingEdgeRef.current === 'end' &&
                    event.currentTarget.hasPointerCapture(event.pointerId)
                  ) {
                    updateTimeFromPointer(event, 'end')
                  }
                }}
                onPointerUp={(event) => {
                  draggingEdgeRef.current = null
                  event.currentTarget.releasePointerCapture(event.pointerId)
                }}
              />
            </>
          )}
        </div>
        <div className="text-muted-foreground relative mt-1 h-4 text-[11px]">
          {range ? (
            <>
              <span
                className="absolute top-0 font-mono tabular-nums"
                style={{ left: `${startLabelLeft}%`, transform: startLabelTransform }}
              >
                {formatTimelineMinute(range.start)}
              </span>
              <span
                className="absolute top-0 font-mono tabular-nums"
                style={{ left: `${endLabelLeft}%`, transform: endLabelTransform }}
              >
                {formatTimelineMinute(range.end)}
              </span>
            </>
          ) : (
            <span className="font-mono tabular-nums">{time || '-'}</span>
          )}
        </div>
      </div>
      <div className="flex min-w-0 items-center gap-2">
        <Slider
          value={[value]}
          min={0}
          max={1}
          step={0.01}
          onValueChange={(values) => setValue(clampTalkFrequencyValue(values[0] ?? 0))}
          showValue
          valueFormat="fixed-2"
        />
        <span className="w-10 text-right font-mono text-xs tabular-nums">{value.toFixed(2)}</span>
      </div>
      <div className="flex justify-end gap-2">
        <Button
          type="button"
          size="sm"
          disabled={saveMutation.isPending}
          onClick={() => saveMutation.mutate()}
        >
          {saveMutation.isPending ? '保存中...' : isNewRule ? '新增' : '保存'}
        </Button>
        {!isNewRule && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="text-destructive hover:text-destructive h-8 w-8"
            disabled={deleteMutation.isPending}
            aria-label={`删除时间段 ${rule.time || '默认'} 的发言频率规则`}
            onClick={() => deleteMutation.mutate()}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  )
}

/** 时间轴编辑器容器 */
function TalkFrequencyTimelineEditor({
  detail,
  exactRules,
}: {
  detail: ChatStreamDetail
  exactRules: ChatTalkFrequencyRule[]
}) {
  return (
    <div className="space-y-2">
      <div className="text-muted-foreground hidden grid-cols-[minmax(12rem,1fr)_8rem_8rem] gap-3 px-3 text-[11px] xl:grid">
        <div>时间轴</div>
        <div>频率</div>
        <div className="text-right">操作</div>
      </div>
      {exactRules.length === 0 ? (
        <div className="text-muted-foreground rounded-md border border-dashed px-3 py-2 text-sm">
          当前聊天流还没有专属发言频率规则。
        </div>
      ) : (
        <div className="space-y-2">
          {exactRules.map((rule, index) => (
            <TalkFrequencyTimelineRule key={`${rule.time}:${index}`} detail={detail} rule={rule} />
          ))}
        </div>
      )}
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Plus className="h-4 w-4" />
          新增规则
        </div>
        <TalkFrequencyTimelineRule detail={detail} />
      </div>
    </div>
  )
}

/** 频率编辑器（双模式：时间轴/普通） */
function TalkFrequencyEditor({ detail }: { detail: ChatStreamDetail }) {
  const exactRules = useMemo(() => getExactTalkRules(detail), [detail])
  const [mode, setMode] = useState<TalkFrequencyEditMode>('timeline')

  return (
    <div className="bg-muted/10 space-y-3 rounded-md border p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-sm font-medium">当前聊天流规则</div>
          <div className="text-muted-foreground mt-1 text-xs">
            仅编辑 {detail.platform}:{detail.target_id}:{getChatTypeText(detail.chat_type)}{' '}
            的精确规则。
          </div>
        </div>
        <div className="bg-background inline-flex shrink-0 rounded-md border p-1">
          <Button
            type="button"
            size="sm"
            variant={mode === 'timeline' ? 'secondary' : 'ghost'}
            className="h-7"
            onClick={() => setMode('timeline')}
          >
            时间轴
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mode === 'input' ? 'secondary' : 'ghost'}
            className="h-7"
            onClick={() => setMode('input')}
          >
            普通
          </Button>
        </div>
      </div>

      {mode === 'timeline' ? (
        <TalkFrequencyTimelineEditor detail={detail} exactRules={exactRules} />
      ) : (
        <div className="space-y-3">
          {exactRules.length === 0 ? (
            <div className="text-muted-foreground rounded-md border border-dashed px-3 py-2 text-sm">
              当前聊天流还没有专属发言频率规则。
            </div>
          ) : (
            <div className="space-y-2">
              {exactRules.map((rule, index) => (
                <TalkFrequencyRuleEditor
                  key={`${rule.time}:${index}`}
                  detail={detail}
                  rule={rule}
                />
              ))}
            </div>
          )}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Plus className="h-4 w-4" />
              新增规则
            </div>
            <TalkFrequencyRuleEditor detail={detail} />
          </div>
        </div>
      )}
    </div>
  )
}

/** 发言频率规则区块（详情弹窗第三区块） */
function TalkFrequencySection({ detail }: { detail: ChatStreamDetail }) {
  return (
    <section className="space-y-3 rounded-md border p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="font-medium">发言频率规则</div>
        <StatusBadge enabled={detail.talk_frequency.enabled} />
      </div>
      <div className="grid gap-2 text-sm sm:grid-cols-3">
        <FrequencySummaryItem label="默认频率" value={detail.talk_frequency.base_value_label} />
        <FrequencySummaryItem
          label="当前生效"
          value={detail.talk_frequency.effective_value_label}
        />
        <FrequencySummaryItem
          formatValue={false}
          label="当前时间"
          value={detail.talk_frequency.current_time}
        />
      </div>
      <div className="space-y-2">
        {detail.talk_frequency.matched_rules.length === 0 ? (
          <div className="bg-muted text-muted-foreground rounded-md px-3 py-2 text-sm">
            没有可应用的动态发言频率规则，使用默认频率。
          </div>
        ) : (
          detail.talk_frequency.matched_rules.map((rule, index) => (
            <TalkFrequencyRuleStackItem
              key={`${rule.platform}:${rule.item_id}:${rule.time}:${index}`}
              rule={rule}
            />
          ))
        )}
      </div>
      <TalkFrequencyEditor detail={detail} />
    </section>
  )
}

export {
  FrequencySummaryItem,
  StatusBadge,
  TalkFrequencyEditor,
  TalkFrequencyRuleEditor,
  TalkFrequencyRuleStackItem,
  TalkFrequencySection,
  TalkFrequencyTimelineEditor,
  TalkFrequencyTimelineRule,
}