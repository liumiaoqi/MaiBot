import { ChevronDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'

import { normalizeToolDefinition } from '../utils/tag-parse'

export function ToolDefinitionsCollapsible({ toolDefinitions }: { toolDefinitions: unknown[] }) {
  const tools = toolDefinitions.map(normalizeToolDefinition)

  return (
    <Collapsible className="rounded-md border">
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="hover:bg-muted/50 flex w-full items-center justify-between gap-2 px-2.5 py-2 text-left text-sm transition-colors sm:px-3 [&[data-state=open]>svg]:rotate-180"
        >
          <span className="font-medium">工具定义 · {tools.length} 个</span>
          <ChevronDown className="h-4 w-4 shrink-0 transition-transform" />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="border-t">
        <div className="space-y-2 p-2 sm:p-3">
          {tools.map((tool, index) => (
            <div key={`${tool.name}-${index}`} className="bg-background/60 rounded-md border p-2.5 sm:p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary" className="font-mono">
                  {tool.name}
                </Badge>
                <span className="text-muted-foreground text-xs">{tool.type}</span>
              </div>
              {tool.description && (
                <p className="text-foreground mt-2 text-sm leading-6">{tool.description}</p>
              )}

              {tool.parameters.length > 0 ? (
                <div className="mt-3 space-y-2">
                  <div className="text-muted-foreground text-xs font-medium">参数</div>
                  <div className="space-y-1.5">
                    {tool.parameters.map((parameter) => (
                      <div key={parameter.name} className="rounded-md border px-2.5 py-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-sm font-semibold">{parameter.name}</span>
                          <Badge variant="outline" className="px-1.5 py-0 font-mono text-[11px]">
                            {parameter.type}
                          </Badge>
                          {parameter.required && (
                            <Badge
                              variant="outline"
                              className="border-destructive/50 px-1.5 py-0 text-[11px] text-destructive"
                            >
                              必填
                            </Badge>
                          )}
                        </div>
                        {parameter.description && (
                          <p className="text-muted-foreground mt-1 text-xs leading-5">
                            {parameter.description}
                          </p>
                        )}
                        {(parameter.enumValues.length > 0 || parameter.defaultValue) && (
                          <div className="text-muted-foreground mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
                            {parameter.enumValues.length > 0 && (
                              <span>可选值：{parameter.enumValues.join('、')}</span>
                            )}
                            {parameter.defaultValue && <span>默认：{parameter.defaultValue}</span>}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-muted-foreground mt-3 text-xs">无参数</div>
              )}

              <Collapsible className="mt-3 rounded-md border">
                <CollapsibleTrigger asChild>
                  <button
                    type="button"
                    className="hover:bg-muted/50 flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left text-xs transition-colors [&[data-state=open]>svg]:rotate-180"
                  >
                    <span>原始定义</span>
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 transition-transform" />
                  </button>
                </CollapsibleTrigger>
                <CollapsibleContent className="border-t">
                  <pre className="p-2.5 font-mono text-xs leading-5 whitespace-pre-wrap">
                    {JSON.stringify(tool.raw, null, 2)}
                  </pre>
                </CollapsibleContent>
              </Collapsible>
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}