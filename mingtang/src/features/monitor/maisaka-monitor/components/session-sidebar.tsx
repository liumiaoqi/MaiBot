/**
 * SessionSidebar 会话侧边栏
 *
 * 按 lastActivity 倒序排列会话，展示会话名/事件计数/最近活动相对时间/当前阶段状态。
 * 折叠时仅展示头像列。空状态占位。
 */
import { Bot } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import type { SessionInfo, StageStatusInfo } from '../hooks/persist-monitor'
import { cn } from '@/lib/utils'

import { SessionAvatar } from './session-avatar'
import { formatRelativeTime } from './timeline-entry-item'

export interface SessionSidebarProps {
  sessions: Map<string, SessionInfo>
  stageStatuses: Map<string, StageStatusInfo>
  selectedSession: string | null
  onSelect: (id: string) => void
  collapsed: boolean
}

export function SessionSidebar({
  sessions,
  stageStatuses,
  selectedSession,
  onSelect,
  collapsed,
}: SessionSidebarProps) {
  const { t } = useTranslation()
  const sortedSessions = Array.from(sessions.values()).sort(
    (a, b) => b.lastActivity - a.lastActivity,
  )

  if (sortedSessions.length === 0) {
    if (collapsed) {
      return <div className="h-full p-2" />
    }

    return (
      <div className={cn(
        'flex flex-col items-center justify-center h-full text-muted-foreground gap-2',
        'p-4',
      )}>
        <Bot className="h-8 w-8 opacity-40" />
        <p className="text-sm text-center">{t('monitor.maisaka.waitingSession')}</p>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col gap-1', collapsed ? 'items-center p-2' : 'p-2')}>
      {sortedSessions.map((session) => {
        const status = stageStatuses.get(session.sessionId)
        const rel = formatRelativeTime(session.lastActivity)
        return (
          <button
            key={session.sessionId}
            onClick={() => onSelect(session.sessionId)}
            title={session.sessionName}
            className={cn(
              'max-w-full overflow-hidden rounded-lg text-left text-sm transition-colors',
              'hover:bg-accent/50',
              collapsed
                ? 'flex h-10 w-10 items-center justify-center p-0'
                : 'flex w-full min-w-0 flex-col items-start gap-0.5 px-2.5 py-2',
              selectedSession === session.sessionId && 'bg-accent text-accent-foreground',
            )}
          >
            <div className={cn('flex w-full min-w-0 items-center', collapsed ? 'justify-center' : 'justify-between gap-2')}>
              <div className={cn('flex min-w-0 items-center gap-2 overflow-hidden', !collapsed && 'flex-1')}>
                <SessionAvatar session={session} stageStatus={status} collapsed={collapsed} />
                {!collapsed && (
                  <span
                    className="block min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-medium"
                    title={session.sessionName}
                  >
                    {session.sessionName}
                  </span>
                )}
              </div>
              {!collapsed && (
                <Badge variant="secondary" className="h-4 shrink-0 px-1 text-[10px]">
                  {session.eventCount}
                </Badge>
              )}
            </div>
            {!collapsed && (
              <div className="flex w-full min-w-0 items-center justify-between gap-2 overflow-hidden text-xs text-muted-foreground">
                <span className="shrink-0">{t(rel.key, rel.options)}</span>
                {status && <span className="min-w-0 truncate text-primary">{status.stage}</span>}
              </div>
            )}
          </button>
        )
      })}
    </div>
  )
}