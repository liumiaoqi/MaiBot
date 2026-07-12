import { useQuery } from '@tanstack/react-query'
import { ArrowUpDown, MessageSquare } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getChatStreams, type ChatStream } from '@/lib/chat-management-api'

type SortField = 'last_active' | 'message_count'
type SortDir = 'asc' | 'desc'

function formatRelativeTime(timestamp: number | null): string {
  if (!timestamp) return '--'
  const diff = Date.now() / 1000 - timestamp
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return `${Math.floor(diff / 86400)} 天前`
}

export function ChatStreamMonitor() {
  const { t } = useTranslation()
  const [sortField, setSortField] = useState<SortField>('last_active')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { data: streams = [], isLoading } = useQuery({
    queryKey: ['chat-streams', 'monitor'],
    queryFn: () => getChatStreams(500),
    staleTime: 30_000,
  })

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const sorted = [...streams].sort((a, b) => {
    let va: number, vb: number
    if (sortField === 'last_active') {
      va = a.last_active_at ?? 0
      vb = b.last_active_at ?? 0
    } else {
      va = a.message_count
      vb = b.message_count
    }
    return sortDir === 'asc' ? va - vb : vb - va
  })

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex h-5 items-center gap-2 text-sm font-medium leading-5">
          <MessageSquare className="h-4 w-4" />
          {t('monitor.chatStream.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="mb-3 flex items-center gap-2">
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => toggleSort('last_active')}>
            <ArrowUpDown className="mr-1 h-3 w-3" />
            {t('monitor.chatStream.lastActive')}
          </Button>
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => toggleSort('message_count')}>
            <ArrowUpDown className="mr-1 h-3 w-3" />
            {t('monitor.chatStream.messageCount')}
          </Button>
        </div>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('monitor.chatStream.loading')}</p>
        ) : sorted.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('monitor.chatStream.empty')}</p>
        ) : (
          <div className="max-h-[400px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="pb-2 pr-3 font-medium">{t('monitor.chatStream.name')}</th>
                  <th className="pb-2 pr-3 font-medium">{t('monitor.chatStream.agent')}</th>
                  <th className="pb-2 pr-3 font-medium text-right">{t('monitor.chatStream.messages')}</th>
                  <th className="pb-2 font-medium text-right">{t('monitor.chatStream.lastActive')}</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((stream) => (
                  <tr key={stream.session_id} className="border-b last:border-0">
                    <td className="py-2 pr-3 max-w-[200px] truncate">
                      {stream.display_name || stream.session_id}
                    </td>
                    <td className="py-2 pr-3 max-w-[100px] truncate">
                      {stream.agent_display_name || stream.agent_id}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {stream.message_count}
                    </td>
                    <td className="py-2 text-right text-xs text-muted-foreground">
                      {formatRelativeTime(stream.last_active_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}