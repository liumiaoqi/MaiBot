/**
 * 聊天主面板顶部信息栏（孤儿复用——ADR-6 选项 A）。
 *
 * 从 dashboard routes/chat/ChatHeaderBar.tsx 搬移适配（166 行——行为等价）。
 * 原版 ChatHeaderBar 是孤儿组件（bars.test 引用但未挂载到页面）——R3 复用到 /chat 头部。
 *
 * 适配点：
 * - 去掉 AgentIndicator（agent 域是 R4 范围——R3 chat 域先不接 agent 指示器）
 * - 去掉 agentId/agentDisplayName/agentColor/onAgentClick props（留待 R4 接入）
 * - bg-primary-gradient → bg-primary（mingtang 无 gradient class）
 *
 * 核心职责（REQ-R3-04）：头像/标题/连接状态指示点 + 重连按钮 + 虚拟会话身份信息。
 */
import { Bot, Loader2, RefreshCw, UserCircle2, Users, Wifi, WifiOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useResolvedAvatarUrl } from '@/lib/avatar-url'
import { cn } from '@/lib/utils'

import type { ChatTab } from '../types'

interface ChatHeaderBarProps {
  activeTab: ChatTab | undefined
  botDisplayName: string
  isConnecting: boolean
  isLoadingHistory: boolean
  onReconnect: () => void
}

/**
 * 聊天主面板顶部信息栏：展示当前会话头像、标题、连接状态以及操作按钮。
 */
export function ChatHeaderBar({
  activeTab,
  botDisplayName,
  isConnecting,
  isLoadingHistory,
  onReconnect,
}: ChatHeaderBarProps) {
  const { t } = useTranslation()

  const isVirtual = activeTab?.type === 'virtual'
  const virtualConfig = activeTab?.virtualConfig
  const connected = activeTab?.isConnected ?? false
  const botAvatarUrl = useResolvedAvatarUrl('qq', activeTab?.sessionInfo.bot_qq)

  return (
    <header className="bg-card/85 supports-backdrop-filter:bg-card/65 relative z-1 shrink-0 border-b backdrop-blur">
      <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-6 sm:py-4">
        <div className="flex min-w-0 items-center gap-3">
          {/* 头像 + 在线状态指示点 */}
          <div className="relative shrink-0">
            <Avatar className="h-10 w-10 ring-1 ring-border/60 sm:h-11 sm:w-11">
              {botAvatarUrl && (
                <AvatarImage
                  src={botAvatarUrl}
                  alt={`${botDisplayName} 的头像`}
                  className="object-cover"
                />
              )}
              <AvatarFallback className="bg-primary text-primary-foreground">
                <Bot className="h-5 w-5" />
              </AvatarFallback>
            </Avatar>
            <span
              aria-hidden="true"
              className={cn(
                'absolute right-0 bottom-0 h-3 w-3 rounded-full border-2 border-card transition-colors',
                connected
                  ? 'bg-emerald-500'
                  : isConnecting
                    ? 'bg-amber-500'
                    : 'bg-muted-foreground/60'
              )}
            />
          </div>

          {/* 标题与副标题 */}
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold leading-tight sm:text-base">
              {botDisplayName}
            </h1>
            <div className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-xs leading-tight">
              {connected ? (
                <>
                  <Wifi className="h-3 w-3 text-emerald-500" />
                  <span>{t('chat.status.connected')}</span>
                </>
              ) : isConnecting ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>{t('chat.status.connecting')}</span>
                </>
              ) : (
                <>
                  <WifiOff className="h-3 w-3 text-rose-500" />
                  <span>{t('chat.status.disconnected')}</span>
                </>
              )}

              {isVirtual && virtualConfig && (
                <>
                  <span aria-hidden className="text-muted-foreground/40">
                    ·
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <UserCircle2 className="h-3 w-3" />
                    <span className="max-w-40 truncate">{virtualConfig.userName}</span>
                  </span>
                  <span className="bg-muted text-muted-foreground rounded-full px-1.5 py-0.5 text-[10px] font-medium">
                    {virtualConfig.platform}
                  </span>
                  {virtualConfig.groupName && (
                    <span className="hidden items-center gap-1 sm:inline-flex">
                      <Users className="h-3 w-3" />
                      <span className="max-w-40 truncate">{virtualConfig.groupName}</span>
                    </span>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {/* 右侧操作 */}
        <div className="flex shrink-0 items-center gap-1">
          {isLoadingHistory && (
            <Loader2 className="text-muted-foreground h-4 w-4 animate-spin" aria-hidden="true" />
          )}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                aria-label={t('chat.actions.reconnect')}
                className="h-9 w-9 rounded-full"
                disabled={isConnecting}
                size="icon"
                variant="ghost"
                onClick={onReconnect}
              >
                <RefreshCw className={cn('h-4 w-4', isConnecting && 'animate-spin')} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{t('chat.actions.reconnect')}</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </header>
  )
}