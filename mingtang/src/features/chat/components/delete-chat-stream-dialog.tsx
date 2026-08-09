/**
 * DeleteChatStreamDialog 严肃确认删除流（R3-2-4）
 *
 * 从 dashboard routes/chat-management.tsx 1711-1873 行搬移。
 * 危险说明框 + 必须输入完整 session_id + 分阶段进度 12→35→82→100% + 明细汇总
 *
 * 适配点：
 * - useToast → sonner toast()
 * - DialogBody → ScrollArea（R3-W-12 教训）
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  deleteChatStream,
  type ChatStream,
  type ChatStreamDeleteResult,
} from '@/lib/chat-management-api'
import { toast } from 'sonner'

/** 格式化删除明细汇总 */
function formatDeleteSummary(result: ChatStreamDeleteResult): string {
  const visibleItems = result.items.filter((item) => item.count > 0 || (item.unlinked ?? 0) > 0)
  if (visibleItems.length === 0) {
    return '未发现可清理的数据。'
  }

  return visibleItems
    .map((item) => {
      if (item.key === 'jargons') {
        return `${item.label} 删除 ${item.count} 条，解除关联 ${item.unlinked ?? 0} 条`
      }
      return `${item.label} ${item.count} 条`
    })
    .join('；')
}

/** 删除聊天流对话框（严肃确认） */
function DeleteChatStreamDialog({
  chat,
  onDeleted,
  onOpenChange,
}: {
  chat: ChatStream | null
  onDeleted: (sessionId: string) => void
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [confirmText, setConfirmText] = useState('')
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('等待确认')
  const [deleteResult, setDeleteResult] = useState<ChatStreamDeleteResult | null>(null)
  const deleteMutation = useMutation({
    mutationFn: (sessionId: string) => deleteChatStream(sessionId),
  })
  const isDeleting = deleteMutation.isPending
  const canDelete =
    Boolean(chat?.session_id) &&
    confirmText.trim() === chat?.session_id &&
    !isDeleting &&
    !deleteResult

  useEffect(() => {
    if (!chat) {
      const frameId = window.requestAnimationFrame(() => {
        setConfirmText('')
        setProgress(0)
        setStage('等待确认')
        setDeleteResult(null)
      })

      return () => window.cancelAnimationFrame(frameId)
    }
  }, [chat])

  const handleDelete = async () => {
    if (!chat || !canDelete) {
      return
    }

    setDeleteResult(null)
    setProgress(12)
    setStage('提交删除请求')
    try {
      setProgress(35)
      setStage('清理聊天流关联数据')
      const result = await deleteMutation.mutateAsync(chat.session_id)
      setProgress(82)
      setStage('刷新聊天流列表')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['chat-streams'] }),
        queryClient.removeQueries({ queryKey: ['chat-stream-detail', chat.session_id] }),
      ])
      setProgress(100)
      setStage('删除完成')
      setDeleteResult(result)
      onDeleted(chat.session_id)
      toast.success('聊天流已删除', {
        description: formatDeleteSummary(result),
      })
    } catch (error) {
      setProgress(0)
      setStage('删除失败')
      toast.error('删除聊天流失败', {
        description: error instanceof Error ? error.message : '请稍后重试',
      })
    }
  }

  return (
    <Dialog open={chat !== null} onOpenChange={(open) => !isDeleting && onOpenChange(open)}>
      <DialogContent className="max-w-[min(calc(100vw-2rem),38rem)]">
        <DialogHeader>
          <DialogTitle className="text-destructive flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            严肃确认：删除聊天流
          </DialogTitle>
          <DialogDescription>
            此操作不可撤销。删除后会清理所有与该 session_id 直接相关的数据。
          </DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[calc(100vh-16rem)]">
          <div className="pr-4 space-y-4">
            <div className="border-destructive/40 bg-destructive/10 rounded-md border p-3 text-sm">
              <div className="text-destructive font-medium">将被清理的数据包括：</div>
              <ul className="text-muted-foreground mt-2 list-disc space-y-1 pl-5">
                <li>聊天流记录和该 session_id 下的所有消息。</li>
                <li>表达学习、黑话关联、工具调用记录、行为学习记录。</li>
                <li>消息统计、高频词等以该聊天流为归属的数据。</li>
              </ul>
            </div>

            <div className="grid gap-2 text-sm">
              <div className="bg-muted/30 grid gap-1 rounded-md border p-3">
                <span className="text-muted-foreground">聊天流</span>
                <span className="font-medium">{chat?.display_name || '-'}</span>
                <span className="text-muted-foreground font-mono text-xs break-all">
                  {chat?.session_id || '-'}
                </span>
              </div>
              <Label htmlFor="delete-chat-session-confirm">请输入完整 session_id 以确认删除</Label>
              <Input
                id="delete-chat-session-confirm"
                value={confirmText}
                disabled={isDeleting}
                onChange={(event) => setConfirmText(event.target.value)}
                placeholder={chat?.session_id}
                className="font-mono text-xs"
              />
            </div>

            {(isDeleting || progress > 0 || deleteResult) && (
              <div className="space-y-2 rounded-md border p-3">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium">{stage}</span>
                  <span className="text-muted-foreground font-mono text-xs tabular-nums">
                    {progress}%
                  </span>
                </div>
                <Progress value={progress} className="h-2" />
                {deleteResult && (
                  <p className="text-muted-foreground text-xs">
                    {formatDeleteSummary(deleteResult)}
                  </p>
                )}
              </div>
            )}
          </div>
        </ScrollArea>
        <DialogFooter>
          <Button variant="outline" disabled={isDeleting} onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button variant="destructive" disabled={!canDelete} onClick={() => void handleDelete()}>
            {isDeleting ? '删除中...' : '永久删除'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export { DeleteChatStreamDialog, formatDeleteSummary }