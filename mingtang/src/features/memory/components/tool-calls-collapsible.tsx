import { ChevronDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

import { stringifyStructuredValue } from '../utils/format'
import {
  getToolCallSourceClassName,
  normalizeToolCallForDisplay,
} from '../utils/tag-parse'

export function ToolCallsCollapsible({ toolCalls }: { toolCalls: unknown[] }) {
  const displayToolCalls = toolCalls.map(normalizeToolCallForDisplay)

  return (
    <Collapsible className="bg-background/60 mt-2 rounded-md border sm:mt-3">
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="hover:bg-muted/50 flex w-full items-center justify-between gap-2 px-2.5 py-2 text-left text-sm transition-colors sm:px-3 [&[data-state=open]>svg]:rotate-180"
        >
          <span className="font-medium">工具调用 · {toolCalls.length} 个</span>
          <ChevronDown className="h-4 w-4 shrink-0 transition-transform" />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="border-t">
        <div className="space-y-2 p-2.5 sm:p-3">
          {displayToolCalls.map((toolCall, index) => (
            <div key={`${toolCall.id || toolCall.name}-${index}`} className="rounded-md border bg-background/70 p-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary" className="font-mono">
                  {toolCall.name}
                </Badge>
                {toolCall.sourceLabel && (
                  <Badge
                    variant="outline"
                    className={cn('px-1.5 py-0 text-[11px]', getToolCallSourceClassName(toolCall.source))}
                  >
                    {toolCall.sourceLabel}
                  </Badge>
                )}
                {toolCall.id && (
                  <span className="text-muted-foreground font-mono text-[11px]">
                    {toolCall.id}
                  </span>
                )}
              </div>
              <pre className="mt-2 rounded-md border bg-muted/20 p-2 font-mono text-xs leading-5 whitespace-pre-wrap">
                {stringifyStructuredValue(toolCall.arguments)}
              </pre>
            </div>
          ))}
          <Collapsible className="rounded-md border">
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="hover:bg-muted/50 flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left text-xs transition-colors [&[data-state=open]>svg]:rotate-180"
              >
                <span>完整工具调用 JSON</span>
                <ChevronDown className="h-3.5 w-3.5 shrink-0 transition-transform" />
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="border-t">
              <pre className="p-2.5 font-mono text-xs leading-5 whitespace-pre-wrap">
                {JSON.stringify(toolCalls, null, 2)}
              </pre>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
