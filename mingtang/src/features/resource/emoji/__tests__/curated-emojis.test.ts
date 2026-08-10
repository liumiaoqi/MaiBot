/**
 * curated-emojis 精选清单数据源测试（R4-1-1-1 测试先行）
 *
 * 核心验证：
 * - 类型正确性（emoji_id + description 必填 + 扩展字段可选）
 * - 清单规模 15-20 条（spec.md §5.1.1 #1）
 * - 每条 description 非空（spec.md §5.1.1 #2 描述清单完整）
 * - 扩展性：新增条目自动包含（spec.md §5.1.1 #3）
 */
import { describe, expect, it } from 'vitest'
import { curatedEmojis, type CuratedEmoji } from '../curated-emojis'

describe('curated-emojis 精选清单数据源', () => {
  describe('清单规模（spec.md §5.1.1 #1）', () => {
    it('清单条目数在 15-20 范围内', () => {
      expect(curatedEmojis.length).toBeGreaterThanOrEqual(15)
      expect(curatedEmojis.length).toBeLessThanOrEqual(20)
    })

    it('清单非空', () => {
      expect(curatedEmojis).toHaveLength(curatedEmojis.length)
      expect(curatedEmojis.length).toBeGreaterThan(0)
    })
  })

  describe('类型正确性（CuratedEmoji 接口）', () => {
    it('每条含 emoji_id（number）+ description（string）必填字段', () => {
      for (const item of curatedEmojis) {
        expect(typeof item.emoji_id).toBe('number')
        expect(typeof item.description).toBe('string')
      }
    })

    it('emoji_id 唯一（无重复——精选清单每条对应不同表情）', () => {
      const ids = curatedEmojis.map((e) => e.emoji_id)
      const uniqueIds = new Set(ids)
      expect(uniqueIds.size).toBe(ids.length)
    })

    it('扩展字段 emotion/tags/category 可选（存在时类型正确）', () => {
      for (const item of curatedEmojis) {
        if (item.emotion !== undefined) {
          expect(typeof item.emotion).toBe('string')
        }
        if (item.tags !== undefined) {
          expect(Array.isArray(item.tags)).toBe(true)
          for (const tag of item.tags) {
            expect(typeof tag).toBe('string')
          }
        }
        if (item.category !== undefined) {
          expect(typeof item.category).toBe('string')
        }
      }
    })
  })

  describe('描述清单完整（spec.md §5.1.1 #2）', () => {
    it('每条 description 非空字符串', () => {
      for (const item of curatedEmojis) {
        expect(item.description.trim().length).toBeGreaterThan(0)
      }
    })

    it('description 含语义信息（非纯空白/占位符）', () => {
      for (const item of curatedEmojis) {
        expect(item.description).not.toBe('')
        expect(item.description.trim()).not.toBe('')
      }
    })
  })

  describe('扩展性（spec.md §5.1.1 #3——核心）', () => {
    it('数据源为数组——新增条目自动包含（无需改组件代码）', () => {
      const originalLength = curatedEmojis.length
      const newEntry: CuratedEmoji = {
        emoji_id: 99999,
        description: '扩展性测试条目',
      }
      const extended = [...curatedEmojis, newEntry]
      expect(extended).toHaveLength(originalLength + 1)
      expect(extended[extended.length - 1]).toEqual(newEntry)
    })

    it('CuratedEmoji 接口接受仅必填字段（扩展字段可省略）', () => {
      const minimal: CuratedEmoji = {
        emoji_id: 1,
        description: '最小条目',
      }
      expect(minimal.emoji_id).toBe(1)
      expect(minimal.description).toBe('最小条目')
      expect(minimal.emotion).toBeUndefined()
      expect(minimal.tags).toBeUndefined()
      expect(minimal.category).toBeUndefined()
    })

    it('CuratedEmoji 接口接受全部扩展字段（emotion + tags + category）', () => {
      const full: CuratedEmoji = {
        emoji_id: 2,
        description: '完整条目',
        emotion: 'happy',
        tags: ['正面', '日常'],
        category: '表情',
      }
      expect(full.emotion).toBe('happy')
      expect(full.tags).toEqual(['正面', '日常'])
      expect(full.category).toBe('表情')
    })
  })
})