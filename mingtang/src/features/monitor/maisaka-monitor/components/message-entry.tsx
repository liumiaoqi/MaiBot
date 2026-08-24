/**
 * MessageEntry 消息条目（ingested/sent 共用）
 *
 * 头像 + 发言者 + 内容 + 回复预览 + 媒体。
 * 复用 MonitorAvatar + MessageMediaContent + ReplyPreviewBlock。
 */
import { Bot } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import type { MessageIngestedEvent, MessageSentEvent } from '@/lib/maisaka-monitor-client'
import { cn } from '@/lib/utils'

import { MessageMediaContent } from './message-media-content'
import { MonitorAvatar } from './monitor-avatar'
import { ReplyPreviewBlock } from './reply-preview-block'
import { formatTimestamp } from './timeline-entry-item'

export interface MessageEntryProps {
  data: MessageIngestedEvent | MessageSentEvent
  kind: 'ingested' | 'sent'
}

function getMessageInitial(name: string): string {
  const trimmed = name.trim()
  return trimmed ? trimmed.slice(0, 1) : '人'
}

export function MessageEntry({ data, kind }: MessageEntryProps) {
  const { t } = useTranslation()
  const isSent = kind === 'sent'
  const speakerLabel = data.speaker_name || (isSent ? t('monitor.maisaka.maimai') : t('monitor.maisaka.user'))

  return (
    <div className={cn(
      'flex items-start gap-3',
      isSent && 'rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2',
    )}>
      <MonitorAvatar
        className="mt-1 h-7 w-7 rounded-full"
        fallback={isSent ? <Bot className="h-3.5 w-3.5" /> : getMessageInitial(data.speaker_name)}
        fallbackClassName={cn(
          'text-xs font-semibold',
          isSent ? 'bg-emerald-500/15 text-emerald-500' : 'bg-blue-500/15 text-blue-500',
        )}
        label={speakerLabel}
        platform={data.platform}
        targetId={data.user_id}
        targetType="user"
      />
      <div className="flex-1 min-w-0">
        <div className="mb-1 flex items-center gap-2">
          <span className="font-medium text-sm">{speakerLabel}</span>
          {isSent && (
            <Badge variant="outline" className="text-[10px]">{t('monitor.maisaka.sent')}</Badge>
          )}
          {isSent && 'source_kind' in data && data.source_kind && (
            <Badge variant="secondary" className="text-[10px]">{data.source_kind}</Badge>
          )}
          <span className="text-xs text-muted-foreground">{formatTimestamp(data.timestamp)}</span>
        </div>
        <ReplyPreviewBlock replyTo={data.reply_to} />
        <MessageMediaContent
          content={data.content}
          emptyLabel={isSent ? t('monitor.maisaka.nonTextMessage') : t('monitor.maisaka.emptyMessage')}
          media={data.media}
        />
      </div>
    </div>
  )
}