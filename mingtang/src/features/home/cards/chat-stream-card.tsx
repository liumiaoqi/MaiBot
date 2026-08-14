import { Link } from '@tanstack/react-router'
import { MessageSquare } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { AgentStatsInfo, RecentActivity } from '../types'

interface ChatStreamCardProps {
  agentStats: AgentStatsInfo | undefined
  recentActivity: RecentActivity[]
}

/** 今日日期键（模块级常量——渲染期纯度：不在渲染中 new Date() 取当前时刻；跨零点需刷新页面更新） */
const TODAY_KEY = new Date().toDateString()

export function ChatStreamCard({ agentStats, recentActivity }: ChatStreamCardProps) {
  const { t } = useTranslation()

  // 渲染期只做纯数据过滤：活动时间与 TODAY_KEY 比较（无副作用、无当前时刻依赖）
  const todayActivity = recentActivity.filter(
    (a) => new Date(a.timestamp).toDateString() === TODAY_KEY,
  )

  return (
    <Link to={"/chat-management" as never} className="block h-full">
      <Card className="h-full transition-colors hover:border-primary/30">
        <CardHeader className="pb-3">
          <CardTitle className="flex h-5 items-center gap-2 text-sm font-medium leading-5">
            <MessageSquare className="h-4 w-4" />
            {t('home.chatStream.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-muted-foreground">{t('home.chatStream.activeSessions')}</span>
              <span className="text-2xl font-bold text-primary">
                {agentStats?.total_active_sessions ?? '--'}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-muted-foreground">{t('home.chatStream.todayCalls')}</span>
              <span className="text-sm font-medium">
                {todayActivity.length}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}