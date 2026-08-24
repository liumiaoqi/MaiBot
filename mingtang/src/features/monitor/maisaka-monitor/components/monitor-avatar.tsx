/**
 * MonitorAvatar 头像基组件
 *
 * 封装 Avatar + useResolvedAvatarUrl，供 SessionAvatar / MessageEntry 复用。
 * 纯展示——不直接调 WebSocket 或 IndexedDB。
 */
import type { ReactNode } from 'react'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { useResolvedAvatarUrl, type AvatarTargetType } from '@/lib/avatar-url'
import { cn } from '@/lib/utils'

export interface MonitorAvatarProps {
  className?: string
  fallback: ReactNode
  fallbackClassName?: string
  label: string
  platform?: string | null
  targetId?: string | null
  targetType: AvatarTargetType
}

export function MonitorAvatar({
  className,
  fallback,
  fallbackClassName,
  label,
  platform,
  targetId,
  targetType,
}: MonitorAvatarProps) {
  const avatarUrl = useResolvedAvatarUrl(platform, targetId, targetType)

  return (
    <Avatar className={cn('shrink-0 ring-1 ring-border/60', className)}>
      {avatarUrl && <AvatarImage src={avatarUrl} alt={`${label} 的头像`} className="object-cover" />}
      <AvatarFallback className={fallbackClassName}>
        {fallback}
      </AvatarFallback>
    </Avatar>
  )
}