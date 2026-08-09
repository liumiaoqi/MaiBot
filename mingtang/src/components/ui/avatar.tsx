/**
 * Avatar 头像组件（shadcn/ui 标准——基于 @radix-ui/react-avatar）
 *
 * 用于聊天消息气泡头像、用户身份卡等场景。
 */
import * as AvatarPrimitive from '@radix-ui/react-avatar'
import type { ComponentProps } from 'react'

import { cn } from '@/lib/utils'

const Avatar = AvatarPrimitive.Root

const AvatarImage = ({
  className,
  ...props
}: ComponentProps<typeof AvatarPrimitive.Image>) => (
  <AvatarPrimitive.Image
    className={cn('aspect-square h-full w-full', className)}
    {...props}
  />
)

const AvatarFallback = ({
  className,
  ...props
}: ComponentProps<typeof AvatarPrimitive.Fallback>) => (
  <AvatarPrimitive.Fallback
    className={cn(
      'flex h-full w-full items-center justify-center rounded-full bg-muted text-sm font-medium',
      className
    )}
    {...props}
  />
)

export { Avatar, AvatarFallback, AvatarImage }