import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

import type { ChatMessage, MessageSegment } from './types'

// 渲染单个消息段
export function RenderMessageSegment({ segment }: { segment: MessageSegment }) {
  const { t } = useTranslation()

  switch (segment.type) {
    case 'text':
      return <span className="whitespace-pre-wrap">{String(segment.data)}</span>

    case 'image':
    case 'emoji': {
      const mediaLabel = segment.type === 'emoji' ? t('chat.media.emoji') : t('chat.media.image')

      return (
        <img
          src={String(segment.data)}
          alt={mediaLabel}
          className={cn(
            'max-w-full rounded-lg',
            segment.type === 'emoji' ? 'max-h-32' : 'max-h-64'
          )}
          loading="lazy"
          onError={(e) => {
            // 图片加载失败时显示占位符
            const target = e.target as HTMLImageElement
            target.style.display = 'none'
            const fallback = document.createElement('span')
            fallback.className = 'text-muted-foreground text-xs'
            fallback.textContent = t('chat.media.loadFailed', { type: mediaLabel })
            target.parentElement?.appendChild(fallback)
          }}
        />
      )
    }

    case 'voice':
      return (
        <div className="flex items-center gap-2">
          <audio controls src={String(segment.data)} className="h-8 max-w-[200px]">
            <track kind="captions" src="" label={t('chat.media.noCaptions')} default />
            {t('chat.media.audioUnsupported')}
          </audio>
        </div>
      )

    case 'video':
      return (
        <video controls src={String(segment.data)} className="max-h-64 max-w-full rounded-lg">
          <track kind="captions" src="" label={t('chat.media.noCaptions')} default />
          {t('chat.media.videoUnsupported')}
        </video>
      )

    case 'face':
      // QQ 原生表情，显示为文本
      return (
        <span className="text-muted-foreground">
          {t('chat.media.face', { data: String(segment.data) })}
        </span>
      )

    case 'music':
      return <span className="text-muted-foreground">{t('chat.media.music')}</span>

    case 'file':
      return (
        <span className="text-muted-foreground">
          {t('chat.media.file', { data: String(segment.data) })}
        </span>
      )

    case 'reply':
      return <span className="text-muted-foreground text-xs">{t('chat.media.reply')}</span>

    case 'forward':
      return <span className="text-muted-foreground">{t('chat.media.forward')}</span>

    case 'unknown':
    default:
      return (
        <span className="text-muted-foreground">
          {t('chat.media.unknown', {
            type: segment.original_type || t('chat.media.unknownMessage'),
          })}
        </span>
      )
  }
}

// 渲染消息内容（支持富文本）
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function RenderMessageContent({
  message,
  isBot: _isBot,
}: {
  message: ChatMessage
  isBot: boolean
}) {
  // 如果是富文本消息，渲染消息段
  if (message.message_type === 'rich' && message.segments && message.segments.length > 0) {
    return (
      <div className="flex flex-col gap-2">
        {message.segments.map((segment, index) => (
          <RenderMessageSegment key={index} segment={segment} />
        ))}
      </div>
    )
  }

  // 普通文本消息
  return <span className="whitespace-pre-wrap">{message.content}</span>
}
