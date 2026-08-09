import { Cpu, Timer } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import { NaturalLanguageText } from './natural-language-text'
import { ToolCallsCollapsible } from './tool-calls-collapsible'
import {
  formatDurationMs,
  getStructuredPromptMessageRoleStyle,
  stringifyPromptContent,
  type StructuredPromptPayload,
} from '../utils/format'
import {
  isBotSelfStructuredMessage,
  type ReasoningPromptMessageAvatarMap,
} from '../utils/tag-parse'

export function ProviderResponseTimeline({
  structuredPrompt,
  messageAvatarMap = {},
  botSelfNames = new Set<string>(),
}: {
  structuredPrompt: StructuredPromptPayload
  messageAvatarMap?: ReasoningPromptMessageAvatarMap
  botSelfNames?: Set<string>
}) {
  return (
    <div className="space-y-2 p-2 sm:space-y-3 sm:p-3">
      {structuredPrompt.jargon_learning_calls &&
        structuredPrompt.jargon_learning_calls.length > 0 && (
          <div className="space-y-3">
            {structuredPrompt.jargon_learning_calls.map((llmCall, callIndex) => (
              <div
                key={`${llmCall.inference_stage}-${callIndex}`}
                className="space-y-2 rounded-md border p-2.5 sm:p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">
                    #{callIndex + 1} {llmCall.inference_stage}
                  </Badge>
                  {llmCall.metadata?.model_name && (
                    <span className="text-muted-foreground inline-flex items-center gap-1 text-xs">
                      <Cpu className="h-3.5 w-3.5" />
                      {llmCall.metadata.model_name}
                    </span>
                  )}
                  {typeof llmCall.metadata?.duration_ms === 'number' && (
                    <span className="text-muted-foreground inline-flex items-center gap-1 text-xs">
                      <Timer className="h-3.5 w-3.5" />
                      {formatDurationMs(llmCall.metadata.duration_ms)}
                    </span>
                  )}
                </div>

                <div className="space-y-2">
                  {(llmCall.messages ?? []).map((message, messageIndex) => {
                    const isBotSelfMessage = isBotSelfStructuredMessage(message, botSelfNames)
                    const roleStyle = getStructuredPromptMessageRoleStyle(
                      message.role,
                      isBotSelfMessage
                    )
                    return (
                      <div
                        key={`${message.index ?? messageIndex}-${message.role ?? 'unknown'}`}
                        className={cn(
                          'relative rounded-md border px-2.5 pt-9 pb-2.5 sm:px-3 sm:pt-10 sm:pb-3',
                          roleStyle.containerClassName
                        )}
                      >
                        <div className="absolute top-1.5 left-1.5 flex flex-wrap items-center gap-1.5 sm:top-2 sm:left-2">
                          <span className="text-muted-foreground px-1 text-[11px] font-semibold">
                            输入 #{message.index ?? messageIndex + 1}
                          </span>
                          <span className="text-muted-foreground px-1 text-[11px] font-semibold">
                            {roleStyle.label}
                          </span>
                          {message.tool_call_id && (
                            <span className="text-muted-foreground text-xs">
                              tool_call_id: {message.tool_call_id}
                            </span>
                          )}
                        </div>
                        <NaturalLanguageText
                          text={stringifyPromptContent(message.content) || '空内容'}
                          avatarMap={messageAvatarMap}
                        />
                        {message.tool_calls && message.tool_calls.length > 0 && (
                          <ToolCallsCollapsible toolCalls={message.tool_calls} />
                        )}
                      </div>
                    )
                  })}
                </div>

                {llmCall.output && (
                  <div className="rounded-md border p-2.5 sm:p-3">
                    <Badge variant="outline" className="mb-2">
                      {llmCall.output.title || '输出结果'}
                    </Badge>
                    <NaturalLanguageText
                      text={stringifyPromptContent(llmCall.output.content) || '空输出'}
                      avatarMap={messageAvatarMap}
                    />
                    {llmCall.output.tool_calls &&
                      llmCall.output.tool_calls.length > 0 && (
                        <ToolCallsCollapsible toolCalls={llmCall.output.tool_calls} />
                      )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

      {structuredPrompt.output && (
        <div className="rounded-md border p-2.5 sm:p-3">
          <Badge variant="secondary" className="mb-2">
            {structuredPrompt.output.title || '输出结果'}
          </Badge>
          <NaturalLanguageText
            text={stringifyPromptContent(structuredPrompt.output.content) || '空输出'}
            avatarMap={messageAvatarMap}
          />
          {structuredPrompt.output.tool_calls &&
            structuredPrompt.output.tool_calls.length > 0 && (
              <ToolCallsCollapsible toolCalls={structuredPrompt.output.tool_calls} />
            )}
        </div>
      )}

      <div className="space-y-2">
        {(structuredPrompt.messages ?? []).map((message, index) => {
          const isBotSelfMessage = isBotSelfStructuredMessage(message, botSelfNames)
          const roleStyle = getStructuredPromptMessageRoleStyle(
            message.role,
            isBotSelfMessage
          )
          return (
            <div
              key={`${message.index ?? index}-${message.role ?? 'unknown'}`}
              className={cn('relative rounded-md border px-2.5 pt-9 pb-2.5 sm:px-3 sm:pt-10 sm:pb-3', roleStyle.containerClassName)}
            >
              <div className="absolute top-1.5 left-1.5 flex flex-wrap items-center gap-1.5 sm:top-2 sm:left-2">
                <span className="text-muted-foreground px-1 text-[11px] font-semibold">
                  #{message.index ?? index + 1}
                </span>
                <span className="text-muted-foreground px-1 text-[11px] font-semibold">
                  {roleStyle.label}
                </span>
                {message.tool_call_id && (
                  <span className="text-muted-foreground text-xs">
                    tool_call_id: {message.tool_call_id}
                  </span>
                )}
              </div>
              <NaturalLanguageText
                text={stringifyPromptContent(message.content) || '空内容'}
                avatarMap={messageAvatarMap}
              />
              {message.tool_calls && message.tool_calls.length > 0 && (
                <ToolCallsCollapsible toolCalls={message.tool_calls} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}