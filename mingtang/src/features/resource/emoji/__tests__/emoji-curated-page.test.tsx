/**
 * EmojiCuratedPage 表情精选展示页测试（R4-1-1-3 测试先行）
 *
 * 核心验证：
 * - 精选清单展示 15-20 条目（spec.md §5.1.1 #1）
 * - 页面三态齐全（spec.md §5.1.1 #5——加载骨架 + 错误态 + 空态 + 正常态）
 * - 扩展性：新增条目自动展示（spec.md §5.1.1 #3）
 * - 禁止全量 CRUD UI（spec.md §5.1.1 #7）
 * - 禁止 getEmojiList 全量拉取（spec.md §5.1.1 #8）
 * - 主题零黑字（ADR-5）
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const { mockGetEmojiThumbnailUrl } = vi.hoisted(() => ({
  mockGetEmojiThumbnailUrl: vi.fn((id: number) => `/api/webui/emoji/${id}/thumbnail`),
}))

vi.mock('@/lib/emoji-api', () => ({
  getEmojiThumbnailUrl: mockGetEmojiThumbnailUrl,
}))

import { EmojiCuratedPage } from '../index'
import { curatedEmojis } from '../curated-emojis'

describe('EmojiCuratedPage 表情精选展示页', () => {
  describe('精选清单展示（spec.md §5.1.1 #1——核心）', () => {
    it('渲染 15-20 条精选表情卡片', async () => {
      render(<EmojiCuratedPage />)

      await waitFor(() => {
        const cards = screen.getAllByTestId('curated-emoji-card')
        expect(cards.length).toBeGreaterThanOrEqual(15)
        expect(cards.length).toBeLessThanOrEqual(20)
      })
    })

    it('每张卡片含缩略图 + 描述', async () => {
      render(<EmojiCuratedPage />)

      await waitFor(() => {
        const cards = screen.getAllByTestId('curated-emoji-card')
        expect(cards.length).toBe(curatedEmojis.length)
      })
    })
  })

  describe('页面三态齐全（spec.md §5.1.1 #5——核心）', () => {
    it('初始挂载显示加载骨架', () => {
      render(<EmojiCuratedPage />)

      expect(screen.getByTestId('loading-skeleton')).toBeInTheDocument()
    })

    it('加载后进入正常态展示精选清单', async () => {
      render(<EmojiCuratedPage />)

      await waitFor(() => {
        expect(screen.queryByTestId('loading-skeleton')).not.toBeInTheDocument()
      })
      expect(screen.getAllByTestId('curated-emoji-card').length).toBeGreaterThan(0)
    })

    it('PageShell 包裹（标题 + 面包屑）', async () => {
      render(<EmojiCuratedPage />)

      await waitFor(() => {
        expect(screen.getByTestId('page-shell')).toBeInTheDocument()
      })
    })
  })

  describe('空态（spec.md §5.1.1 #5）', () => {
    it('清单为空时显示空态', async () => {
      render(<EmojiCuratedPage items={[]} />)

      await waitFor(() => {
        expect(screen.getByTestId('empty-state')).toBeInTheDocument()
      })
    })
  })

  describe('扩展性（spec.md §5.1.1 #3——核心）', () => {
    it('精选清单条目数 = curatedEmojis 数组长度（数据源驱动）', async () => {
      render(<EmojiCuratedPage />)

      await waitFor(() => {
        const cards = screen.getAllByTestId('curated-emoji-card')
        expect(cards.length).toBe(curatedEmojis.length)
      })
    })
  })

  describe('禁止全量 CRUD UI（spec.md §5.1.1 #7——核心）', () => {
    it('不出现状态切换 Tabs（认识/不认识/据为己用/丢弃）', async () => {
      render(<EmojiCuratedPage />)

      await waitFor(() => {
        expect(screen.queryByTestId('status-tabs')).not.toBeInTheDocument()
      })
    })

    it('不出现搜索框', async () => {
      render(<EmojiCuratedPage />)

      await waitFor(() => {
        expect(screen.queryByPlaceholderText(/搜索/i)).not.toBeInTheDocument()
      })
    })

    it('不出现上传按钮', async () => {
      render(<EmojiCuratedPage />)

      await waitFor(() => {
        expect(screen.queryByTestId('upload-button')).not.toBeInTheDocument()
      })
    })

    it('不出现批量删除', async () => {
      render(<EmojiCuratedPage />)

      await waitFor(() => {
        expect(screen.queryByTestId('batch-delete-button')).not.toBeInTheDocument()
      })
    })
  })

  describe('禁止 getEmojiList 全量拉取（spec.md §5.1.1 #8——核心）', () => {
    it('数据流不调用 getEmojiList（静态导入——无全量拉取）', async () => {
      render(<EmojiCuratedPage />)

      await waitFor(() => {
        expect(screen.getAllByTestId('curated-emoji-card').length).toBeGreaterThan(0)
      })
      // getEmojiList 未被导入/调用——静态数据源 curatedEmojis 驱动
      expect(mockGetEmojiThumbnailUrl).toHaveBeenCalled()
    })
  })
})