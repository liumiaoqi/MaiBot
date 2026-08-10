/**
 * CuratedEmojiCard 精选表情卡片测试（R4-1-1-2 测试先行）
 *
 * 核心验证：
 * - 缩略图通过 getEmojiThumbnailUrl 拼接 URL（spec.md §5.1.1 #4）
 * - 描述文本渲染（spec.md §5.1.1 #2）
 * - 缩略图加载失败兜底（spec.md §5.1.3 #2——onError 触发 onLoadError + 兜底占位）
 * - 扩展字段 emotion/tags/category 展示（可选）
 * - 主题零黑字（ADR-5——文字显式 text-foreground/text-muted-foreground）
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const { mockGetEmojiThumbnailUrl } = vi.hoisted(() => ({
  mockGetEmojiThumbnailUrl: vi.fn((id: number) => `/api/webui/emoji/${id}/thumbnail`),
}))

vi.mock('@/lib/emoji-api', () => ({
  getEmojiThumbnailUrl: mockGetEmojiThumbnailUrl,
}))

import { CuratedEmojiCard } from '../components/curated-emoji-card'
import type { CuratedEmoji } from '../curated-emojis'

function makeEmoji(overrides: Partial<CuratedEmoji> = {}): CuratedEmoji {
  return {
    emoji_id: 42,
    description: '开心——嘴角上扬的笑脸',
    ...overrides,
  }
}

describe('CuratedEmojiCard 精选表情卡片', () => {
  describe('缩略图展示（spec.md §5.1.1 #4）', () => {
    it('通过 getEmojiThumbnailUrl 拼接 URL 并渲染 <img>', () => {
      const emoji = makeEmoji({ emoji_id: 42 })
      render(<CuratedEmojiCard emoji={emoji} />)

      const img = screen.getByRole('img', { name: '开心——嘴角上扬的笑脸' })
      expect(img).toBeInTheDocument()
      expect(mockGetEmojiThumbnailUrl).toHaveBeenCalledWith(42)
      expect(img).toHaveAttribute('src', '/api/webui/emoji/42/thumbnail')
    })

    it('alt 文本使用 description', () => {
      const emoji = makeEmoji({ description: '思考——手托下巴若有所思' })
      render(<CuratedEmojiCard emoji={emoji} />)

      const img = screen.getByRole('img', { name: '思考——手托下巴若有所思' })
      expect(img).toHaveAttribute('alt', '思考——手托下巴若有所思')
    })
  })

  describe('描述文本展示（spec.md §5.1.1 #2）', () => {
    it('渲染 description 文本', () => {
      const emoji = makeEmoji({ description: '委屈——撇嘴低头' })
      render(<CuratedEmojiCard emoji={emoji} />)

      expect(screen.getByText('委屈——撇嘴低头')).toBeInTheDocument()
    })
  })

  describe('缩略图加载失败兜底（spec.md §5.1.3 #2——核心）', () => {
    it('onError 触发 onLoadError 回调（传递 emoji_id）', () => {
      const onLoadError = vi.fn()
      const emoji = makeEmoji({ emoji_id: 99 })
      render(<CuratedEmojiCard emoji={emoji} onLoadError={onLoadError} />)

      const img = screen.getByRole('img')
      fireEvent.error(img)

      expect(onLoadError).toHaveBeenCalledWith(99)
    })

    it('onError 后显示兜底占位（不阻断整页）', () => {
      const emoji = makeEmoji()
      render(<CuratedEmojiCard emoji={emoji} />)

      const img = screen.getByRole('img')
      fireEvent.error(img)

      expect(screen.getByTestId('emoji-thumbnail-fallback')).toBeInTheDocument()
    })

    it('未传 onLoadError 时不抛错（可选回调）', () => {
      const emoji = makeEmoji()
      render(<CuratedEmojiCard emoji={emoji} />)

      const img = screen.getByRole('img')
      expect(() => fireEvent.error(img)).not.toThrow()
    })
  })

  describe('扩展字段展示（可选——不破坏现有展示）', () => {
    it('emotion 存在时展示', () => {
      const emoji = makeEmoji({ emotion: 'happy' })
      render(<CuratedEmojiCard emoji={emoji} />)

      expect(screen.getByText('happy')).toBeInTheDocument()
    })

    it('tags 存在时展示全部标签', () => {
      const emoji = makeEmoji({ tags: ['正面', '日常'] })
      render(<CuratedEmojiCard emoji={emoji} />)

      expect(screen.getByText('正面')).toBeInTheDocument()
      expect(screen.getByText('日常')).toBeInTheDocument()
    })

    it('category 存在时展示', () => {
      const emoji = makeEmoji({ category: '基础情绪' })
      render(<CuratedEmojiCard emoji={emoji} />)

      expect(screen.getByText('基础情绪')).toBeInTheDocument()
    })

    it('扩展字段均不传时不渲染扩展区域', () => {
      const emoji = makeEmoji()
      render(<CuratedEmojiCard emoji={emoji} />)

      expect(screen.queryByTestId('emoji-extension-fields')).not.toBeInTheDocument()
    })
  })
})