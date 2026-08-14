/**
 * Sortable 卡片包装（R4 债清理 P1——从 home-card-manager.tsx 机械拆分）
 *
 * 职责：编辑模式下的拖拽手柄/隐藏按钮/毛玻璃遮罩 + 卡片渲染容器。
 */
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { PluginHomeCardWidth } from '@/lib/plugin-api'
import { cardWidthClass, type HomeCardDefinition } from '../lib/card-layout'

export function stringArraysEqual(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index])
}

export function SortableHomeCard({
  card,
  displayWidth,
  editing,
  onHide,
}: {
  card: HomeCardDefinition
  displayWidth?: PluginHomeCardWidth
  editing: boolean
  onHide: (id: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: card.id,
    disabled: !editing,
  })
  const style = {
    transform: CSS.Translate.toString(transform),
    transition,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn('relative h-full min-w-0', cardWidthClass(displayWidth ?? card.width), isDragging && 'z-20 opacity-80')}
    >
      {editing && (
        <div
          data-home-card-edit-overlay="true"
          aria-hidden="true"
          className="absolute inset-0 z-10 rounded-lg border border-primary/25 bg-white/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.38),inset_0_0_0_1px_rgba(255,255,255,0.12)] backdrop-blur-md backdrop-saturate-150 dark:bg-black/20"
          style={{
            WebkitBackdropFilter: 'blur(10px) saturate(140%)',
            backdropFilter: 'blur(10px) saturate(140%)',
          }}
        />
      )}
      {editing && (
        <div className="absolute right-2 top-2 z-20 flex items-center gap-1 rounded-md border bg-background/95 p-1 shadow-sm backdrop-blur">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" className="h-7 w-7 cursor-grab" {...attributes} {...listeners}>
                <GripVertical className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>拖拽排序</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => onHide(card.id)}
              >
                <X className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>从首页隐藏</TooltipContent>
          </Tooltip>
        </div>
      )}
      <div
        aria-hidden={editing}
        className={cn(
          'h-full overflow-hidden transition-[filter,opacity] duration-150',
          editing && 'pointer-events-none select-none blur-[2.5px] opacity-75'
        )}
        inert={editing}
      >
        {card.render()}
      </div>
    </div>
  )
}
