/**
 * MaisakaMonitorPage MaiSaka 实时监控页
 *
 * 定位：实时展示 MaiSaka 推理引擎事件流（WebSocket 订阅）
 * 数据流：useMaisakaMonitor（WebSocket → monitorState → 组件）
 * 约束：子组件纯展示，副作用集中在 hook
 * i18n：monitor.maisaka.*
 */
import { Activity, ChevronLeft, ChevronRight } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { PageShell } from '@/components/biz/page-shell'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

import { SessionSidebar } from './components/session-sidebar'
import { StageStatusPanel } from './components/stage-status-panel'
import { TimelineStream } from './components/timeline-stream'
import { useMaisakaMonitor } from './hooks/use-maisaka-monitor'

export function MaisakaMonitorPage() {
  const { t } = useTranslation()
  const {
    timeline,
    sessions,
    stageStatuses,
    selectedSession,
    setSelectedSession,
    connected,
    backgroundCollection,
    setBackgroundCollectionEnabled,
    clearTimeline,
  } = useMaisakaMonitor()

  const viewportRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return true
    return window.localStorage.getItem('maisaka-monitor-sidebar-collapsed') !== 'false'
  })

  useEffect(() => {
    window.localStorage.setItem('maisaka-monitor-sidebar-collapsed', String(sidebarCollapsed))
  }, [sidebarCollapsed])

  const scrollToBottom = useCallback(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' })
    setAutoScroll(true)
  }, [])

  const selectedStageStatus = selectedSession ? stageStatuses.get(selectedSession) : undefined

  const stats = {
    messages: timeline.filter((e) => e.type === 'message.ingested' || e.type === 'message.sent').length,
    cycles: timeline.filter((e) => e.type === 'planner.finalized').length,
    toolCalls: timeline.reduce((count, entry) => {
      if (entry.type === 'planner.finalized') {
        const data = entry.data as { tools?: unknown[] }
        return count + (data.tools?.length ?? 0)
      }
      return count
    }, 0),
  }

  return (
    <PageShell title={t('monitor.maisaka.title')}>
      <div className="flex min-w-0 flex-col gap-4 lg:h-[calc(100vh-116px)] lg:flex-row">
        {/* 会话侧边栏 */}
        <aside className={cn(
          'flex min-w-0 shrink-0 flex-col overflow-hidden border border-border bg-background/45 transition-[width] duration-200',
          sidebarCollapsed ? 'w-full lg:w-16' : 'w-full lg:w-52',
        )}>
          <div className={cn('py-2', sidebarCollapsed ? 'px-2' : 'px-3')}>
            <h2 className={cn(
              'text-sm font-medium flex items-center gap-2',
              sidebarCollapsed && 'justify-center text-[0px]',
            )}>
              {!sidebarCollapsed && <Activity className="h-4 w-4" />}
              {t('monitor.maisaka.chatStreams')}
              {connected && (
                <span className={cn('flex h-2 w-2 rounded-full bg-emerald-500', !sidebarCollapsed && 'ml-auto')} />
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                onClick={() => setSidebarCollapsed((value) => !value)}
                title={sidebarCollapsed ? t('monitor.maisaka.expandSidebar') : t('monitor.maisaka.collapseSidebar')}
              >
                {sidebarCollapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
              </Button>
            </h2>
          </div>
          <div className="border-b border-border" />
          <ScrollArea className="max-h-40 flex-1 lg:max-h-none">
            <SessionSidebar
              sessions={sessions}
              stageStatuses={stageStatuses}
              selectedSession={selectedSession}
              onSelect={setSelectedSession}
              collapsed={sidebarCollapsed}
            />
          </ScrollArea>
        </aside>

        {/* 主时间线区域 */}
        <div className="flex min-w-0 flex-1 flex-col">
          <StageStatusPanel
            status={selectedStageStatus}
            stats={stats}
            autoScroll={autoScroll}
            backgroundCollection={backgroundCollection}
            onClearTimeline={clearTimeline}
            onToggleBackgroundCollection={() => setBackgroundCollectionEnabled(!backgroundCollection)}
            onScrollToBottom={scrollToBottom}
          />
          <TimelineStream
            timeline={timeline}
            autoScroll={autoScroll}
            onAutoScrollChange={setAutoScroll}
            viewportRef={viewportRef}
          />
        </div>
      </div>
    </PageShell>
  )
}