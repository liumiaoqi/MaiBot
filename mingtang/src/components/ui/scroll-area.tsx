import * as React from 'react'
import * as ScrollAreaPrimitive from '@radix-ui/react-scroll-area'

import { cn } from '@/lib/utils'

/**
 * ScrollArea 滚动区域组件（shadcn/ui 基础 + chat 域扩展）。
 *
 * R1 基础版仅支持标准 shadcn props；R3 chat 域 MessageList 需要
 * viewportRef（scrollToMessage 跳转）/ contentClassName / viewportClassName /
 * scrollbars 控制——扩展为可选 props，不传时行为不变（向后兼容 R1/R2/TE）。
 */
interface ScrollAreaProps
  extends React.ComponentProps<typeof ScrollAreaPrimitive.Root> {
  viewportRef?: React.RefObject<HTMLDivElement | null>
  viewportClassName?: string
  contentClassName?: string
  scrollbars?: 'vertical' | 'horizontal' | 'both'
}

function ScrollArea({
  className,
  children,
  viewportRef,
  viewportClassName,
  contentClassName,
  scrollbars = 'both',
  ...props
}: ScrollAreaProps) {
  return (
    <ScrollAreaPrimitive.Root
      data-slot="scroll-area"
      className={cn('relative overflow-hidden', className)}
      {...props}
    >
      <ScrollAreaPrimitive.Viewport
        ref={viewportRef}
        data-slot="scroll-area-viewport"
        className={cn(
          'h-full w-full overscroll-contain rounded-[inherit] ring-offset-background focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none [&>div]:!block [&>div]:!min-w-0 [&>div]:w-full',
          viewportClassName
        )}
      >
        <div className={cn('!block h-full w-full !min-w-0', contentClassName)}>{children}</div>
      </ScrollAreaPrimitive.Viewport>
      {scrollbars !== 'horizontal' && <ScrollBar />}
      {scrollbars !== 'vertical' && <ScrollBar orientation="horizontal" />}
      <ScrollAreaPrimitive.Corner />
    </ScrollAreaPrimitive.Root>
  )
}

function ScrollBar({
  className,
  orientation = 'vertical',
  ...props
}: React.ComponentProps<typeof ScrollAreaPrimitive.ScrollAreaScrollbar>) {
  return (
    <ScrollAreaPrimitive.ScrollAreaScrollbar
      data-slot="scroll-area-scrollbar"
      orientation={orientation}
      className={cn(
        'flex touch-none p-0.5 select-none transition-colors',
        orientation === 'vertical' && 'h-full w-2.5 border-l border-l-transparent ltr:[clip-path:inset(0_0_0_100%)] rtl:[clip-path:inset(0_100%_0_0)]',
        orientation === 'horizontal' && 'h-2.5 flex-col border-t border-t-transparent ltr:[clip-path:inset(100%_0_0_0)] rtl:[clip-path:inset(0_0_100%_0)]',
        className
      )}
      {...props}
    >
      <ScrollAreaPrimitive.ScrollAreaThumb
        data-slot="scroll-area-thumb"
        className="bg-border relative flex-1 rounded-full"
      />
    </ScrollAreaPrimitive.ScrollAreaScrollbar>
  )
}

export { ScrollArea, ScrollBar }
