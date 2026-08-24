/**
 * MessageMediaContent 媒体展示
 *
 * 图片/表情包展示。点击切换原文件/识别文本（displayOverrides 本地 state）。
 * 纯展示——不含副作用。
 */
import { ImageIcon } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { MaisakaMessageMedia } from '@/lib/maisaka-monitor-client'
import { cn } from '@/lib/utils'

export interface MessageMediaContentProps {
  content?: string
  emptyLabel: string
  media?: MaisakaMessageMedia[]
}

function buildMessageMediaKey(media: MaisakaMessageMedia, index: number): string {
  return `${media.kind}:${media.hash}:${media.index ?? index}`
}

export function MessageMediaContent({ content, emptyLabel, media = [] }: MessageMediaContentProps) {
  const { t } = useTranslation()
  const [displayOverrides, setDisplayOverrides] = useState<Record<string, boolean>>({})
  const normalizedContent = content ?? ''
  const hasContent = normalizedContent.trim().length > 0
  const hasMedia = media.length > 0

  if (!hasContent && !hasMedia) {
    return (
      <p className="text-sm text-foreground/80 whitespace-pre-wrap wrap-break-word leading-relaxed">
        {emptyLabel}
      </p>
    )
  }

  return (
    <div className="space-y-1.5">
      {hasContent && (
        <p className="text-sm text-foreground/80 whitespace-pre-wrap wrap-break-word leading-relaxed">
          {normalizedContent}
        </p>
      )}
      {hasMedia && (
        <div className="flex flex-wrap gap-2">
          {media.map((item, index) => {
            const mediaKey = buildMessageMediaKey(item, index)
            const source = item.data_url || item.url
            const canShowOriginal = source.trim().length > 0
            const showOriginal = canShowOriginal && (displayOverrides[mediaKey] ?? Boolean(item.default_original))
            const label = item.kind === 'emoji' ? t('monitor.maisaka.emoji') : t('monitor.maisaka.image')
            return (
              <button
                key={mediaKey}
                type="button"
                className={cn(
                  'group max-w-full overflow-hidden rounded-md border bg-muted/40 text-left transition-colors hover:border-primary/60 hover:bg-muted/70',
                  showOriginal ? 'p-1.5' : 'px-2.5 py-1.5',
                )}
                title={t('monitor.maisaka.toggleMedia', {
                  target: showOriginal ? t('monitor.maisaka.recognizedText') : t('monitor.maisaka.originalFile'),
                })}
                onClick={() => {
                  if (!canShowOriginal) {
                    return
                  }
                  setDisplayOverrides((current) => ({
                    ...current,
                    [mediaKey]: !showOriginal,
                  }))
                }}
              >
                {showOriginal ? (
                  <img
                    src={source}
                    alt={`${label}${t('monitor.maisaka.originalFile')}`}
                    className={cn(
                      'block rounded object-contain',
                      item.kind === 'emoji' ? 'max-h-24 max-w-24' : 'max-h-56 max-w-full',
                    )}
                    loading="lazy"
                  />
                ) : (
                  <span className="flex max-w-sm items-center gap-1.5 text-xs text-muted-foreground">
                    <ImageIcon className="h-3.5 w-3.5 shrink-0" />
                    <span className="min-w-0 whitespace-pre-wrap break-words">
                      {item.text || `[${label}]`}
                    </span>
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}