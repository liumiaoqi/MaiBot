import { ChevronDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'

import { ToolCallsCollapsible } from '../tool-calls-collapsible'
import {
  formatEmptyReplayResponseHint,
  formatReplayTokenSummary,
  type ReplayRunResult,
} from '../../utils/replay-prepare'

export function ReplayResultItem({ item }: { item: ReplayRunResult }) {
  const result = item.result

  if (!result) {
    return (
      <div className="space-y-2 rounded-md border p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="destructive">#{item.index} 失败</Badge>
        </div>
        <div className="border-destructive/30 bg-destructive/10 rounded-md border px-3 py-2 text-sm text-destructive">
          {item.error || '请求重放接口失败'}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={!result.error ? 'default' : 'destructive'}>
          #{item.index} {!result.error ? '完成' : '失败'}
        </Badge>
        <span className="text-muted-foreground text-xs">{result.model_name}</span>
      </div>
      <div className="text-muted-foreground text-xs leading-5">
        {formatReplayTokenSummary(result)}
      </div>
      {result.error && (
        <div className="border-destructive/30 bg-destructive/10 rounded-md border px-3 py-2 text-sm text-destructive">
          {result.error}
        </div>
      )}
      {result.response.trim() ? (
        <pre className="bg-muted/30 max-h-56 min-h-24 overflow-auto rounded-md border p-3 text-sm leading-6 whitespace-pre-wrap">
          {result.response}
        </pre>
      ) : (
        <div className="text-muted-foreground rounded-md border border-dashed px-3 py-3 text-sm">
          {formatEmptyReplayResponseHint(result)}
        </div>
      )}
      {result.reasoning.trim() && (
        <Collapsible className="rounded-md border" defaultOpen={!result.response.trim()}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium"
            >
              推理内容
              <ChevronDown className="h-4 w-4" />
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent className="border-t">
            <pre className="max-h-56 overflow-auto p-3 text-sm leading-6 whitespace-pre-wrap">
              {result.reasoning.trim()}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      )}
      {result.tool_calls && result.tool_calls.length > 0 && (
        <ToolCallsCollapsible toolCalls={result.tool_calls} />
      )}
    </div>
  )
}