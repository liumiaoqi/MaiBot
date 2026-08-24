/**
 * ReplyPreviewBlock 回复预览
 *
 * 展示回复预览前缀 + 原文。纯展示。
 */
import { useTranslation } from 'react-i18next'

import type { MaisakaReplyPreview } from '@/lib/maisaka-monitor-client'

export interface ReplyPreviewBlockProps {
  replyTo?: MaisakaReplyPreview | null
}

export function ReplyPreviewBlock({ replyTo }: ReplyPreviewBlockProps) {
  const { t } = useTranslation()

  if (!replyTo) {
    return null
  }

  return (
    <div className="mb-1.5 max-w-xl rounded-md bg-muted/70 px-2.5 py-1.5 text-xs text-muted-foreground">
      <div className="mb-0.5 flex min-w-0 items-center gap-1.5">
        <span className="min-w-0 truncate font-medium text-foreground/80">
          {t('monitor.maisaka.replyTo', { name: replyTo.sender_name || t('monitor.maisaka.unknownUser') })}
        </span>
        {replyTo.message_id && (
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground/70">
            #{replyTo.message_id}
          </span>
        )}
      </div>
      <div className="line-clamp-2 whitespace-pre-wrap break-words leading-4">
        {replyTo.content || t('monitor.maisaka.replyUnavailable')}
      </div>
    </div>
  )
}