/**
 * SessionDetailDialog 详情弹窗（R3-2-3 主组件）
 *
 * 从 dashboard routes/chat-management.tsx 317-334 + 1660-1710 行搬移。
 * 组装五区块：基本信息 + 频率规则 + Prompt + 学习配置
 *
 * 适配点：
 * - dashboard DialogBody → mingtang DialogContent + ScrollArea（R3-W-12 教训）
 * - useToast → sonner toast()
 * - useResolvedAvatarUrl 从 @/lib/avatar-url 导入
 */
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { UserRound, UsersRound } from 'lucide-react'


import type { ChatStream, ChatStreamDetail } from '@/lib/chat-management-api'
import { useResolvedAvatarUrl } from '@/lib/avatar-url'

import { SessionBasicInfo } from './session-basic-info'
import { SessionLearningConfig } from './session-learning-config'
import { SessionPrompts } from './session-prompts'
import { TalkFrequencySection } from './talk-frequency-timeline-rule'

/** 聊天流头像 */
function ChatStreamAvatar({ chat }: { chat: ChatStream }) {
  const targetType = chat.chat_type === 'group' ? 'group' : 'user'
  const targetId = chat.chat_type === 'group' ? chat.group_id : chat.user_id
  const avatarUrl = useResolvedAvatarUrl(chat.platform, targetId, targetType)
  const Icon = chat.chat_type === 'group' ? UsersRound : UserRound

  return (
    <Avatar className="border-border ring-background h-8 w-8 rounded-md border-2 ring-1">
      {avatarUrl && (
        <AvatarImage src={avatarUrl} alt={`${chat.display_name} 的头像`} className="object-cover" />
      )}
      <AvatarFallback className="text-muted-foreground rounded-md">
        <Icon className="h-4 w-4" />
      </AvatarFallback>
    </Avatar>
  )
}

/** 详情内容（三态 + 五区块） */
function ChatDetailContent({
  detail,
  loading,
  error,
}: {
  detail: ChatStreamDetail | undefined
  loading: boolean
  error: unknown
}) {
  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-16" />
        <Skeleton className="h-24" />
        <Skeleton className="h-32" />
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div className="border-destructive/40 text-destructive rounded-md border p-4 text-sm">
        加载详情失败
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <SessionBasicInfo detail={detail} />
      <TalkFrequencySection detail={detail} />
      <SessionPrompts detail={detail} />
      <SessionLearningConfig detail={detail} />
    </div>
  )
}

/** 详情弹窗 */
function SessionDetailDialog({
  chat,
  detail,
  loading,
  error,
  open,
  onOpenChange,
}: {
  chat: ChatStream | null
  detail: ChatStreamDetail | undefined
  loading: boolean
  error: unknown
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[min(calc(100vw-2rem),56rem)]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {chat && <ChatStreamAvatar chat={chat} />}
            <span>{chat?.display_name ?? '聊天流详情'}</span>
          </DialogTitle>
          <DialogDescription>
            查看和编辑聊天流的频率规则、Prompt 与学习配置。
          </DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[calc(100vh-12rem)]">
          <div className="pr-4">
            <ChatDetailContent detail={detail} loading={loading} error={error} />
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}

export { ChatDetailContent, ChatStreamAvatar, SessionDetailDialog }