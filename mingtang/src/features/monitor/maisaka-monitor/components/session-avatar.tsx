/**
 * SessionAvatar 会话头像
 *
 * 复用 MonitorAvatar + 状态点（按 agentState 着色）。
 * 折叠时隐藏状态点（空间紧凑）。
 */
import type { SessionInfo, StageStatusInfo } from '../hooks/persist-monitor'

import type { AvatarTargetType } from '@/lib/avatar-url'
import { cn } from '@/lib/utils'

import { MonitorAvatar } from './monitor-avatar'

export interface SessionAvatarProps {
  session: SessionInfo
  stageStatus?: StageStatusInfo
  collapsed: boolean
}

function getSessionInitial(session: SessionInfo): string {
  const name = session.sessionName.trim()
  return name ? name.slice(0, 1) : (session.isGroupChat ? '群' : '私')
}

function isWaitingForMessage(status: StageStatusInfo): boolean {
  return status.stage === '等待消息' || status.detail.includes('等待消息') || status.agentState === 'wait'
}

export function SessionAvatar({ session, stageStatus, collapsed }: SessionAvatarProps) {
  const targetType: AvatarTargetType = session.isGroupChat ? 'group' : 'user'
  const targetId = session.isGroupChat ? session.groupId : session.userId
  const statusDotClassName = stageStatus && isWaitingForMessage(stageStatus) ? 'bg-blue-500' : 'bg-emerald-500'

  return (
    <span className="relative flex h-7 w-7 shrink-0">
      <MonitorAvatar
        className="h-7 w-7 rounded-md"
        fallback={getSessionInitial(session)}
        fallbackClassName="rounded-md bg-primary/10 text-xs font-semibold text-primary"
        label={session.sessionName}
        platform={session.platform}
        targetId={targetId}
        targetType={targetType}
      />
      {stageStatus && !collapsed && (
        <span className={cn('absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-background', statusDotClassName)} />
      )}
    </span>
  )
}