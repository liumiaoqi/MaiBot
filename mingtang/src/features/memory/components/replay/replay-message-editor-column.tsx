import { Plus, Trash2, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

import type { EditableReplayMessage } from '../../utils/replay-prepare'

export function ReplayMessageEditorColumn({
  selectedTitle,
  messages,
  updateMessage,
  addMessage,
  deleteMessage,
  onClose,
}: {
  selectedTitle: string
  messages: EditableReplayMessage[]
  updateMessage: (id: string, patch: Partial<EditableReplayMessage>) => void
  addMessage: () => void
  deleteMessage: (id: string) => void
  onClose: () => void
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-12 flex-shrink-0 items-center justify-between gap-3 border-b px-3 py-2 sm:min-h-14 sm:px-4 sm:py-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-medium">编辑重放消息</span>
            <Badge variant="secondary">{messages.length} 条</Badge>
          </div>
          <div className="text-muted-foreground mt-1 truncate text-xs">{selectedTitle}</div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5"
            onClick={addMessage}
          >
            <Plus className="h-4 w-4" />
            添加消息
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={onClose}
            title="退出重放编辑"
            aria-label="退出重放编辑"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="divide-y">
          {messages.length === 0 ? (
            <div className="text-muted-foreground px-3 py-10 text-center text-sm">
              这条记录没有可重放的结构化 messages。
            </div>
          ) : (
            messages.map((message, index) => (
              <section key={message.id} className="p-3 sm:p-4">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge variant="outline">#{index + 1}</Badge>
                  <Select
                    value={message.role}
                    onValueChange={(value) => updateMessage(message.id, { role: value })}
                  >
                    <SelectTrigger className="h-8 w-[130px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="system">system</SelectItem>
                      <SelectItem value="user">user</SelectItem>
                      <SelectItem value="assistant">assistant</SelectItem>
                      <SelectItem value="tool">tool</SelectItem>
                    </SelectContent>
                  </Select>
                  {message.tool_call_id && (
                    <span className="text-muted-foreground text-xs">
                      tool_call_id: {message.tool_call_id}
                    </span>
                  )}
                  {message.tool_calls && message.tool_calls.length > 0 && (
                    <Badge variant="secondary">工具调用 {message.tool_calls.length}</Badge>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    className="ml-auto h-8 w-8 p-0"
                    onClick={() => deleteMessage(message.id)}
                    title="删除消息"
                    aria-label={`删除第 ${index + 1} 条消息`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <Textarea
                  value={message.contentText}
                  onChange={(event) => updateMessage(message.id, { contentText: event.target.value })}
                  minHeight={120}
                  maxHeight={420}
                  className="font-mono text-xs leading-5"
                />
              </section>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}