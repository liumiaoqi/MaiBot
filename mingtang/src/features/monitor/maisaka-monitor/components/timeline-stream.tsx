/**
 * TimelineStream 时间线事件流
 *
 * ScrollArea 渲染时间线条目，自动滚动至最新。
 * viewportRef 由父组件持有，用于"回到底部"操作。
 */
import type { RefObject } from 'react'
import { Clock } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { TimelineEntry } from '../hooks/persist-monitor'

import { TimelineEntryItem } from './timeline-entry-item'

export interface TimelineStreamProps {
  timeline: TimelineEntry[]
  autoScroll: boolean
  onAutoScrollChange: (value: boolean) => void
  viewportRef: RefObject<HTMLDivElement | null>
}

export function TimelineStream({ timeline, autoScroll, onAutoScrollChange, viewportRef }: TimelineStreamProps) {
  const { t } = useTranslation()

  // 自动滚动到底部
  useEffect(() => {
    if (autoScroll && viewportRef.current) {
      viewportRef.current.scrollTo({ top: viewportRef.current.scrollHeight, behavior: 'auto' })
    }
  }, [timeline, autoScroll, viewportRef])

  // 监听滚动——用户手动上滚时关闭 autoScroll
  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = viewport
      onAutoScrollChange(scrollHeight - scrollTop - clientHeight < 80)
    }
    viewport.addEventListener('scroll', handleScroll, { passive: true })
    return () => viewport.removeEventListener('scroll', handleScroll)
  }, [onAutoScrollChange, viewportRef])

  return (
    <Card className="min-h-[420px] min-w-0 flex-1 overflow-hidden lg:min-h-0">
      <ScrollArea className="h-full" viewportRef={viewportRef}>
        <div className="min-w-0 space-y-3 p-4">
          {timeline.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-muted-foreground gap-3">
              <Clock className="h-10 w-10 opacity-30" />
              <p className="text-sm">{t('monitor.maisaka.waitingEvents')}</p>
              <p className="text-xs opacity-60">{t('monitor.maisaka.waitingEventsHint')}</p>
            </div>
          ) : (
            timeline.map((entry) => (
              <div
                key={entry.id}
                className="animate-in fade-in-0 slide-in-from-bottom-2 duration-300"
              >
                <TimelineEntryItem entry={entry} />
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </Card>
  )
}