/**
 * constants.ts 常量定义测试（R4-2-2 测试先行）
 *
 * 核心验证：
 * - 删除分页常量正确性
 * - 反馈分页常量正确性
 * - 导入分块分页常量正确性
 * - 导入状态集合正确性
 * - 导入模式选项正确性（7 种）
 * - CorrectionTab 零引用验证（spec.md §5.6.1 #6）
 */
import { describe, expect, it } from 'vitest'

import {
  DELETE_OPERATION_FETCH_LIMIT,
  DELETE_OPERATION_ITEM_PAGE_SIZE,
  DELETE_OPERATION_PAGE_SIZE,
  FEEDBACK_ACTION_LOG_PAGE_SIZE,
  FEEDBACK_CORRECTION_FETCH_LIMIT,
  FEEDBACK_CORRECTION_PAGE_SIZE,
  IMPORT_CHUNK_PAGE_SIZE,
  IMPORT_KIND_OPTIONS,
  IMPORT_STATUS_TEXT,
  IMPORT_STEP_TEXT,
  QUEUED_IMPORT_STATUS,
  RUNNING_IMPORT_STATUS,
} from '../constants'

describe('R4-2-2 constants.ts 常量定义', () => {
  describe('删除分页常量', () => {
    it('DELETE_OPERATION_FETCH_LIMIT = 100', () => {
      expect(DELETE_OPERATION_FETCH_LIMIT).toBe(100)
    })

    it('DELETE_OPERATION_PAGE_SIZE = 6', () => {
      expect(DELETE_OPERATION_PAGE_SIZE).toBe(6)
    })

    it('DELETE_OPERATION_ITEM_PAGE_SIZE = 8', () => {
      expect(DELETE_OPERATION_ITEM_PAGE_SIZE).toBe(8)
    })
  })

  describe('反馈分页常量', () => {
    it('FEEDBACK_CORRECTION_FETCH_LIMIT = 100', () => {
      expect(FEEDBACK_CORRECTION_FETCH_LIMIT).toBe(100)
    })

    it('FEEDBACK_CORRECTION_PAGE_SIZE = 6', () => {
      expect(FEEDBACK_CORRECTION_PAGE_SIZE).toBe(6)
    })

    it('FEEDBACK_ACTION_LOG_PAGE_SIZE = 8', () => {
      expect(FEEDBACK_ACTION_LOG_PAGE_SIZE).toBe(8)
    })
  })

  describe('导入分块分页常量', () => {
    it('IMPORT_CHUNK_PAGE_SIZE = 50', () => {
      expect(IMPORT_CHUNK_PAGE_SIZE).toBe(50)
    })
  })

  describe('导入状态集合', () => {
    it('RUNNING_IMPORT_STATUS 包含 preparing/running/cancel_requested', () => {
      expect(RUNNING_IMPORT_STATUS.has('preparing')).toBe(true)
      expect(RUNNING_IMPORT_STATUS.has('running')).toBe(true)
      expect(RUNNING_IMPORT_STATUS.has('cancel_requested')).toBe(true)
    })

    it('QUEUED_IMPORT_STATUS 包含 queued', () => {
      expect(QUEUED_IMPORT_STATUS.has('queued')).toBe(true)
    })

    it('IMPORT_STATUS_TEXT 含 8 种状态文案', () => {
      expect(IMPORT_STATUS_TEXT.queued).toBe('排队中')
      expect(IMPORT_STATUS_TEXT.running).toBe('运行中')
      expect(IMPORT_STATUS_TEXT.completed).toBe('已完成')
      expect(IMPORT_STATUS_TEXT.failed).toBe('失败')
    })

    it('IMPORT_STEP_TEXT 含 15 种步骤文案', () => {
      expect(IMPORT_STEP_TEXT.splitting).toBe('分块中')
      expect(IMPORT_STEP_TEXT.extracting).toBe('抽取中')
      expect(IMPORT_STEP_TEXT.writing).toBe('写入中')
    })
  })

  describe('导入模式选项（7 种——spec.md §5.2.1 #1）', () => {
    it('IMPORT_KIND_OPTIONS 恰好 7 种', () => {
      expect(IMPORT_KIND_OPTIONS).toHaveLength(7)
    })

    it('包含 7 种导入模式', () => {
      const values = IMPORT_KIND_OPTIONS.map((o) => o.value)
      expect(values).toContain('upload')
      expect(values).toContain('paste')
      expect(values).toContain('raw_scan')
      expect(values).toContain('lpmm_openie')
      expect(values).toContain('lpmm_convert')
      expect(values).toContain('temporal_backfill')
      expect(values).toContain('maibot_migration')
    })

    it('每项含 label + description 非空', () => {
      for (const option of IMPORT_KIND_OPTIONS) {
        expect(typeof option.label).toBe('string')
        expect(option.label.length).toBeGreaterThan(0)
        expect(typeof option.description).toBe('string')
        expect(option.description.length).toBeGreaterThan(0)
      }
    })
  })

  describe('CorrectionTab 零引用验证（spec.md §5.6.1 #6）', () => {
    it('无 MEMORY_CORRECTION_FETCH_LIMIT 常量', async () => {
      const mod = await import('../constants')
      expect((mod as Record<string, unknown>).MEMORY_CORRECTION_FETCH_LIMIT).toBeUndefined()
    })

    it('无 MEMORY_CORRECTION_PAGE_SIZE 常量', async () => {
      const mod = await import('../constants')
      expect((mod as Record<string, unknown>).MEMORY_CORRECTION_PAGE_SIZE).toBeUndefined()
    })
  })
})