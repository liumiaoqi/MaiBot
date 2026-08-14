/**
 * common-params-form —— 公共参数 + 高级参数（Card1 内、7 个模式表单之上）。
 *
 * - 可见 4 项（文件/分块并发 + LLM 抽取 + 聊天日志）沿用旧版边框样式，label/description 取自
 *   COMMON_IMPORT_SCHEMA 声明；动态 min/max（settings 并发上限）在渲染时覆盖；
 * - 归属聊天流是自定义富组件（搜索 + 列表选择），importCommonChatId 本身仍是 schema 字段
 *   （高级参数里还有手动输入框兜底）；
 * - 高级参数 8 项用 SchemaField 渲染，「默认 X」动态前缀的说明由本组件覆盖 description。
 */
import { useMemo, useState } from 'react'

import { Check, Search } from 'lucide-react'

import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

import { buildImportFieldMap, COMMON_IMPORT_SCHEMA } from '../../import-mode-schemas'
import type { UseImportFormResult } from '../../hooks/useImportForm'
import { SchemaField } from './schema-field'
import { filterChatTargets, getChatTargetMetaParts, getChatTargetValueLabel } from './utils'

export function CommonParamsForm({ form }: { form: UseImportFormResult }) {
  const fields = buildImportFieldMap(COMMON_IMPORT_SCHEMA)
  const { importSettings, importChatTargets } = form
  const [chatTargetQuery, setChatTargetQuery] = useState('')
  const selectedImportChatTarget = useMemo(
    () => importChatTargets.find((chat) => chat.chat_id === form.importCommonChatId.trim()),
    [importChatTargets, form.importCommonChatId],
  )
  const visibleImportChatTargets = useMemo(
    () => filterChatTargets(importChatTargets, chatTargetQuery),
    [chatTargetQuery, importChatTargets],
  )
  const importMaxChunkChars = Number.isFinite(Number(importSettings.max_chunk_chars))
    ? Number(importSettings.max_chunk_chars)
    : 3200
  const narrativeWindowForOverlap = Number.isFinite(
    Number(form.importCommonNarrativeWindowSize || importSettings.default_narrative_window_size),
  )
    ? Number(form.importCommonNarrativeWindowSize || importSettings.default_narrative_window_size)
    : 1600

  return (
    <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
      <div className="rounded-md border border-border/60 bg-background/80 px-3 py-2">
        <div className="text-sm font-medium text-foreground">公共参数</div>
        <div className="mt-0.5 text-xs leading-relaxed text-foreground/75">这些设置会应用到当前导入任务。一般保持默认即可，只在批量导入或排查问题时调整。</div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="grid gap-2 rounded-md border bg-background/70 p-3 sm:grid-cols-[minmax(0,1fr)_8rem] sm:items-center">
          <div className="min-w-0">
            <Label>{fields.importCommonFileConcurrency.label}</Label>
            <div className="mt-0.5 text-xs text-muted-foreground">{fields.importCommonFileConcurrency.description}</div>
          </div>
          <Input
            type="number"
            min={1}
            max={Number(importSettings.max_file_concurrency ?? 128)}
            value={form.importCommonFileConcurrency}
            onChange={(event) => form.setImportCommonFileConcurrency(event.target.value)}
          />
        </div>
        <div className="grid gap-2 rounded-md border bg-background/70 p-3 sm:grid-cols-[minmax(0,1fr)_8rem] sm:items-center">
          <div className="min-w-0">
            <Label>{fields.importCommonChunkConcurrency.label}</Label>
            <div className="mt-0.5 text-xs text-muted-foreground">{fields.importCommonChunkConcurrency.description}</div>
          </div>
          <Input
            type="number"
            min={1}
            max={Number(importSettings.max_chunk_concurrency ?? 256)}
            value={form.importCommonChunkConcurrency}
            onChange={(event) => form.setImportCommonChunkConcurrency(event.target.value)}
          />
        </div>
        <div className="rounded-md border bg-background/70 px-2.5 py-2">
          <div className="flex items-center gap-2 text-sm font-medium leading-tight">
            <Checkbox
              checked={form.importCommonLlmEnabled}
              onCheckedChange={(value) => form.setImportCommonLlmEnabled(Boolean(value))}
            />
            {fields.importCommonLlmEnabled.label}
          </div>
          <div className="mt-0.5 pl-6 text-[11px] leading-snug text-muted-foreground">
            {fields.importCommonLlmEnabled.description}
          </div>
        </div>
        <div className="rounded-md border bg-background/70 px-2.5 py-2">
          <div className="flex items-center gap-2 text-sm font-medium leading-tight">
            <Checkbox
              checked={form.importCommonChatLog}
              onCheckedChange={(value) => form.setImportCommonChatLog(Boolean(value))}
            />
            {fields.importCommonChatLog.label}
          </div>
          <div className="mt-0.5 pl-6 text-[11px] leading-snug text-muted-foreground">
            {fields.importCommonChatLog.description}
          </div>
        </div>
        <div className="grid gap-3 rounded-md border bg-background/70 p-3 md:col-span-2 md:grid-cols-[minmax(0,1fr)_minmax(18rem,28rem)]">
          <div className="min-w-0">
            <Label>归属聊天流</Label>
            <div className="mt-0.5 text-xs text-muted-foreground">可输入群号、QQ 号或聊天名检索；选择后，这批记忆只会在对应聊天流的检索中默认出现。</div>
          </div>
          <div className="space-y-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                aria-label="搜索归属聊天流"
                value={chatTargetQuery}
                onChange={(event) => setChatTargetQuery(event.target.value)}
                placeholder="输入群号、QQ 号或聊天名"
                className="pl-9"
              />
            </div>
            <div className="rounded-md border bg-background">
              <button
                type="button"
                className={cn(
                  'flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent',
                  !form.importCommonChatId && 'bg-accent/70',
                )}
                onClick={() => form.setImportCommonChatId('')}
              >
                <Check className={cn('h-4 w-4 shrink-0', !form.importCommonChatId ? 'opacity-100' : 'opacity-0')} />
                <span className="truncate">不绑定聊天流</span>
              </button>
              {visibleImportChatTargets.length > 0 ? (
                <div className="max-h-44 overflow-y-auto border-t">
                  {visibleImportChatTargets.map((chat) => (
                    <button
                      key={chat.chat_id}
                      type="button"
                      className={cn(
                        'flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-accent',
                        form.importCommonChatId.trim() === chat.chat_id && 'bg-accent/70',
                      )}
                      onClick={() => form.setImportCommonChatId(chat.chat_id)}
                    >
                      <Check
                        className={cn(
                          'mt-0.5 h-4 w-4 shrink-0',
                          form.importCommonChatId.trim() === chat.chat_id ? 'opacity-100' : 'opacity-0',
                        )}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{chat.chat_name}</span>
                        <span className="block truncate text-[11px] text-muted-foreground">
                          {getChatTargetMetaParts(chat).join(' · ')}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="border-t px-3 py-3 text-sm text-muted-foreground">没有找到匹配的聊天流</div>
              )}
            </div>
            <div className="truncate text-[11px] leading-snug text-muted-foreground">
              当前选择：{getChatTargetValueLabel(selectedImportChatTarget)}
            </div>
          </div>
        </div>
      </div>

      <details className="rounded-md border bg-background/70 p-3 text-sm">
        <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
          高级参数（通常不用修改）
        </summary>
        <div className="mt-3 grid gap-3">
          <div className="grid gap-3 md:grid-cols-3">
            <SchemaField
              field={fields.importCommonNarrativeWindowSize}
              value={form.importCommonNarrativeWindowSize}
              onChange={(value) => form.setImportCommonNarrativeWindowSize(String(value))}
              max={importMaxChunkChars}
              description={`默认 ${Number(importSettings.default_narrative_window_size ?? 1600)}，用于 narrative/聊天日志。`}
            />
            <SchemaField
              field={fields.importCommonNarrativeOverlap}
              value={form.importCommonNarrativeOverlap}
              onChange={(value) => form.setImportCommonNarrativeOverlap(String(value))}
              max={Math.max(0, narrativeWindowForOverlap - 1)}
              description={`默认 ${Number(importSettings.default_narrative_overlap ?? 400)}，保留跨块上下文。`}
            />
            <SchemaField
              field={fields.importCommonFactualTargetSize}
              value={form.importCommonFactualTargetSize}
              onChange={(value) => form.setImportCommonFactualTargetSize(String(value))}
              max={importMaxChunkChars}
              description={`默认 ${Number(importSettings.default_factual_target_size ?? 1200)}，用于 factual 结构感知切分。`}
            />
          </div>
          <SchemaField
            field={fields.importCommonStrategyOverride}
            value={form.importCommonStrategyOverride}
            onChange={(value) => form.setImportCommonStrategyOverride(String(value))}
          />
          <SchemaField
            field={fields.importCommonDedupePolicy}
            value={form.importCommonDedupePolicy}
            onChange={(value) => form.setImportCommonDedupePolicy(String(value))}
          />
          <SchemaField
            field={fields.importCommonChatReferenceTime}
            value={form.importCommonChatReferenceTime}
            onChange={(value) => form.setImportCommonChatReferenceTime(String(value))}
          />
          <SchemaField
            field={fields.importCommonChatId}
            value={form.importCommonChatId}
            onChange={(value) => form.setImportCommonChatId(String(value))}
            placeholder="留空表示不绑定"
          />
          <SchemaField
            field={fields.importCommonForce}
            value={form.importCommonForce}
            onChange={(value) => form.setImportCommonForce(Boolean(value))}
          />
          <SchemaField
            field={fields.importCommonClearManifest}
            value={form.importCommonClearManifest}
            onChange={(value) => form.setImportCommonClearManifest(Boolean(value))}
          />
        </div>
      </details>
    </div>
  )
}
