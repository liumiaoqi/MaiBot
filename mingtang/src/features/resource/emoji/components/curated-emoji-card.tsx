/**
 * 精选表情卡片（R4-1-1-2）
 *
 * 缩略图通过 getEmojiThumbnailUrl 拼接 URL（HttpOnly Cookie 认证——浏览器自动携带）
 * 加载失败显示兜底占位（不阻断整页）
 * 扩展字段 emotion/tags/category 可选展示
 *
 * design.md §2.2.2.1 / ADR-5 主题零黑字
 */
import { useState } from 'react'
import { ImageIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { getEmojiThumbnailUrl } from '@/lib/emoji-api'
import { cn } from '@/lib/utils'

import type { CuratedEmoji } from '../curated-emojis'

interface CuratedEmojiCardProps {
  /** 精选表情条目 */
  emoji: CuratedEmoji
  /** 缩略图加载失败回调（兜底占位） */
  onLoadError?: (emojiId: number) => void
}

/**
 * 精选表情卡片——缩略图 + 描述 + 加载失败兜底
 */
export function CuratedEmojiCard({ emoji, onLoadError }: CuratedEmojiCardProps): React.ReactElement {
  const [thumbnailFailed, setThumbnailFailed] = useState(false)
  const thumbnailUrl = getEmojiThumbnailUrl(emoji.emoji_id)
  const hasExtension = emoji.emotion !== undefined || emoji.tags !== undefined || emoji.category !== undefined

  return (
    <div
      className="flex flex-col overflow-hidden rounded-lg border bg-card"
      data-testid="curated-emoji-card"
    >
      {/* 缩略图区域 */}
      <div className="relative aspect-square bg-muted">
        {thumbnailFailed ? (
          <div
            className="flex h-full w-full items-center justify-center"
            data-testid="emoji-thumbnail-fallback"
          >
            <ImageIcon className="h-12 w-12 text-muted-foreground" aria-hidden="true" />
          </div>
        ) : (
          <img
            src={thumbnailUrl}
            alt={emoji.description}
            className="h-full w-full object-cover"
            loading="lazy"
            onError={() => {
              setThumbnailFailed(true)
              onLoadError?.(emoji.emoji_id)
            }}
          />
        )}
      </div>

      {/* 描述区域 */}
      <div className="flex flex-1 flex-col gap-2 p-3">
        <p className="text-sm text-foreground leading-relaxed">{emoji.description}</p>

        {/* 扩展字段（可选——不破坏现有展示） */}
        {hasExtension && (
          <div className="flex flex-wrap items-center gap-1.5" data-testid="emoji-extension-fields">
            {emoji.category && (
              <Badge variant="outline" className="text-xs text-foreground">
                {emoji.category}
              </Badge>
            )}
            {emoji.emotion && (
              <Badge variant="secondary" className="text-xs">
                {emoji.emotion}
              </Badge>
            )}
            {emoji.tags?.map((tag) => (
              <Badge
                key={tag}
                variant="outline"
                className={cn('text-xs text-muted-foreground')}
              >
                {tag}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}