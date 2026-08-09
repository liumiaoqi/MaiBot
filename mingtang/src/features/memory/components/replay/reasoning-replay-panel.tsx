import { Loader2, Play, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  replayReasoningPrompt,
  type ReasoningPromptFile,
} from '@/lib/reasoning-process-api'
import { cn } from '@/lib/utils'

import { ReplayResultItem } from './replay-result-item'
import { isRecord, type StructuredPromptPayload } from '../../utils/format'
import {
  parseReplayMessageContent,
  type EditableReplayMessage,
  type ReplayRunResult,
} from '../../utils/replay-prepare'

const REPLAY_COUNT_MAX = 20

export function ReasoningReplayPanel({
  open,
  onClose,
  selected,
  selectedTitle,
  structuredPrompt,
  messages,
}: {
  open: boolean
  onClose: () => void
  selected: ReasoningPromptFile | null
  selectedTitle: string
  structuredPrompt: StructuredPromptPayload | null
  messages: EditableReplayMessage[]
}) {
  const [modelName, setModelName] = useState('')
  const [temperature, setTemperature] = useState('')
  const [maxTokens, setMaxTokens] = useState('')
  const [replayCount, setReplayCount] = useState('1')
  const [replayResults, setReplayResults] = useState<ReplayRunResult[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [runningReplayIndex, setRunningReplayIndex] = useState(0)

  // open/选中参数变化 → 重置表单——渲染期调整模式（审核修复：rAF 规避 → React 官方模式）
  const [prevReplayState, setPrevReplayState] = useState({ open, selected, structuredPrompt })
  if (
    open &&
    (prevReplayState.open !== open ||
      prevReplayState.selected !== selected ||
      prevReplayState.structuredPrompt !== structuredPrompt)
  ) {
    setPrevReplayState({ open, selected, structuredPrompt })
    setModelName(structuredPrompt?.metadata?.model_name || selected?.model_name || '')
    setTemperature('')
    setMaxTokens('')
    setReplayCount('1')
    setReplayResults([])
    setRunningReplayIndex(0)
  }

  const handleReplay = async () => {
    const normalizedModelName = modelName.trim()
    if (!normalizedModelName) {
      toast.error('缺少模型名称', {
        description: '请填写 model_config.toml 中已配置的模型名称。',
      })
      return
    }
    const normalizedReplayCount = Number(replayCount.trim())
    if (!Number.isInteger(normalizedReplayCount) || normalizedReplayCount < 1 || normalizedReplayCount > REPLAY_COUNT_MAX) {
      toast.error('重放次数无效', {
        description: `请输入 1-${REPLAY_COUNT_MAX} 之间的整数。`,
      })
      return
    }
    if (messages.length === 0) {
      toast.error('没有可重放的消息', {
        description: '这条记录没有结构化 messages。',
      })
      return
    }

    setSubmitting(true)
    setReplayResults([])
    setRunningReplayIndex(0)
    let successCount = 0
    const requestMessages = messages.map((message) => ({
      role: message.role,
      content: parseReplayMessageContent(message.contentText, message.originalContent),
      ...(message.tool_call_id ? { tool_call_id: message.tool_call_id } : {}),
      ...(message.tool_calls && message.tool_calls.length > 0 ? { tool_calls: message.tool_calls } : {}),
    }))
    const toolDefinitions = (structuredPrompt?.tool_definitions ?? []).filter(isRecord)

    try {
      for (let index = 1; index <= normalizedReplayCount; index += 1) {
        setRunningReplayIndex(index)
        try {
          const replayResult = await replayReasoningPrompt({
            source_path: selected?.json_path ?? null,
            stage: selected?.stage ?? structuredPrompt?.request?.kind ?? '',
            model_name: normalizedModelName,
            messages: requestMessages,
            tool_definitions: toolDefinitions,
            temperature: temperature.trim() ? Number(temperature) : null,
            max_tokens: maxTokens.trim() ? Number(maxTokens) : null,
          })
          if (!replayResult.error) {
            successCount += 1
          }
          setReplayResults((current) => [
            ...current,
            { id: `${Date.now()}-${index}`, index, result: replayResult, error: null },
          ])
        } catch (err) {
          setReplayResults((current) => [
            ...current,
            {
              id: `${Date.now()}-${index}`,
              index,
              result: null,
              error: err instanceof Error ? err.message : '请求重放接口失败',
            },
          ])
        }
      }
      if (successCount === normalizedReplayCount) {
        toast.success('批量重放完成', {
          description: `成功 ${successCount}/${normalizedReplayCount} 次。`,
        })
      } else {
        toast.error('批量重放完成', {
          description: `成功 ${successCount}/${normalizedReplayCount} 次。`,
        })
      }
    } finally {
      setRunningReplayIndex(0)
      setSubmitting(false)
    }
  }

  return (
    <aside
      className={cn(
        'bg-background min-h-0 flex-col overflow-hidden rounded-md border shadow-sm',
        open ? 'flex' : 'hidden'
      )}
      aria-hidden={!open}
    >
      <div className="flex min-h-14 items-center justify-between gap-3 border-b px-3 py-2 sm:px-4">
        <div className="min-w-0">
          <div className="text-sm font-semibold">重放推理请求</div>
          <div className="text-muted-foreground truncate text-xs">{selectedTitle}</div>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="h-8 w-8 p-0"
          onClick={onClose}
          disabled={submitting}
          title="关闭重放边栏"
          aria-label="关闭重放边栏"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="divide-y">
          <section className="p-3 sm:p-4">
            <div className="grid gap-3">
              <div className="grid gap-2">
                <Label htmlFor="reasoning-replay-model">模型名称</Label>
                <Input
                  id="reasoning-replay-model"
                  value={modelName}
                  onChange={(event) => setModelName(event.target.value)}
                  placeholder="model_config.toml 中的模型名称"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-2">
                  <Label htmlFor="reasoning-replay-temperature">温度</Label>
                  <Input
                    id="reasoning-replay-temperature"
                    type="number"
                    min={0}
                    max={2}
                    step={0.1}
                    value={temperature}
                    onChange={(event) => setTemperature(event.target.value)}
                    placeholder="默认"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="reasoning-replay-max-tokens">最大 Token</Label>
                  <Input
                    id="reasoning-replay-max-tokens"
                    type="number"
                    min={1}
                    step={1}
                    value={maxTokens}
                    onChange={(event) => setMaxTokens(event.target.value)}
                    placeholder="默认"
                  />
                </div>
              </div>
              <div className="grid grid-cols-[minmax(0,1fr)_5.5rem] items-end gap-3">
                <Button
                  className="h-9 w-full gap-1.5"
                  onClick={handleReplay}
                  disabled={submitting || messages.length === 0}
                >
                  {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  {submitting && runningReplayIndex > 0
                    ? `执行中 ${runningReplayIndex}/${replayCount.trim() || '?'}`
                    : '执行重放'}
                </Button>
                <div className="grid gap-2">
                  <Label htmlFor="reasoning-replay-count">次数</Label>
                  <Input
                    id="reasoning-replay-count"
                    type="number"
                    min={1}
                    max={REPLAY_COUNT_MAX}
                    step={1}
                    value={replayCount}
                    onChange={(event) => setReplayCount(event.target.value)}
                  />
                </div>
              </div>
            </div>
          </section>

          <section className="space-y-3 p-3 sm:p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-semibold">重放结果</div>
              {submitting && (
                <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  第 {runningReplayIndex || 1} 次
                </span>
              )}
            </div>
            {replayResults.length === 0 && !submitting ? (
              <div className="text-muted-foreground rounded-md border border-dashed px-3 py-4 text-sm">
                执行重放后，模型回复、推理内容和工具调用会显示在这里。
              </div>
            ) : null}
            {replayResults.length > 0 && (
              <div className="space-y-3">
                {replayResults.map((item) => (
                  <ReplayResultItem key={item.id} item={item} />
                ))}
              </div>
            )}
          </section>

        </div>
      </ScrollArea>
    </aside>
  )
}