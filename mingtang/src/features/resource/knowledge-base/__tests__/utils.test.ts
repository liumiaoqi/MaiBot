/**
 * utils.ts 工具函数测试（R4-2-3 测试先行）
 *
 * 核心验证：
 * - 通用函数正确性
 * - Import 格式化函数正确性
 * - Delete 格式化函数正确性
 * - Feedback 格式化函数正确性
 * - CorrectionTab 零引用验证（spec.md §5.6.1 #7）
 */
import { describe, expect, it } from 'vitest'

import {
  buildFeedbackImpactSummary,
  describeFeedbackActionLog,
  formatDeleteOperationMode,
  formatDeleteOperationStatus,
  formatDeleteOperationTime,
  formatDeleteRelationText,
  formatFeedbackActionType,
  formatFeedbackDecision,
  formatFeedbackRelationTriplet,
  formatFeedbackRollbackStatus,
  formatFeedbackTaskStatus,
  formatImportTime,
  formatProgressPercent,
  getDeleteOperationItemLabel,
  getDeleteOperationItemPreview,
  getDeleteOperationItemSource,
  getFeedbackCorrectionPreview,
  getFeedbackStatusVariant,
  getImportStatusLabel,
  getImportStatusVariant,
  getImportStepLabel,
  normalizeImportInputMode,
  normalizeProgress,
  parseCommaSeparatedList,
  parseOptionalNonNegativeInt,
  parseOptionalPositiveInt,
  pickFeedbackRelationTriplet,
  summarizeFeedbackActionPayload,
  trimDeleteItemText,
} from '../utils'

describe('R4-2-3 utils.ts 工具函数', () => {
  describe('通用函数', () => {
    it('normalizeProgress：0-1 范围转百分比', () => {
      expect(normalizeProgress(0.5)).toBe(50)
      expect(normalizeProgress(1)).toBe(100)
    })

    it('normalizeProgress：>1 直接用', () => {
      expect(normalizeProgress(50)).toBe(50)
      expect(normalizeProgress(100)).toBe(100)
    })

    it('normalizeProgress：边界 clamp', () => {
      expect(normalizeProgress(-10)).toBe(0)
      expect(normalizeProgress(200)).toBe(100)
    })

    it('normalizeProgress：null/undefined → 0', () => {
      expect(normalizeProgress(null)).toBe(0)
      expect(normalizeProgress(undefined)).toBe(0)
    })

    it('formatProgressPercent', () => {
      expect(formatProgressPercent(0.5)).toBe('50.0%')
      expect(formatProgressPercent(100)).toBe('100.0%')
    })

    it('parseOptionalPositiveInt', () => {
      expect(parseOptionalPositiveInt('')).toBeUndefined()
      expect(parseOptionalPositiveInt('42')).toBe(42)
      expect(parseOptionalPositiveInt('-1')).toBeUndefined()
      expect(parseOptionalPositiveInt('0')).toBeUndefined()
      expect(parseOptionalPositiveInt('1.5')).toBeUndefined()
    })

    it('parseOptionalNonNegativeInt', () => {
      expect(parseOptionalNonNegativeInt('')).toBeUndefined()
      expect(parseOptionalNonNegativeInt('0')).toBe(0)
      expect(parseOptionalNonNegativeInt('42')).toBe(42)
      expect(parseOptionalNonNegativeInt('-1')).toBeUndefined()
    })

    it('parseCommaSeparatedList', () => {
      expect(parseCommaSeparatedList('a, b, c')).toEqual(['a', 'b', 'c'])
      expect(parseCommaSeparatedList('')).toEqual([])
      expect(parseCommaSeparatedList('a,,b')).toEqual(['a', 'b'])
    })
  })

  describe('Import 格式化函数', () => {
    it('normalizeImportInputMode', () => {
      expect(normalizeImportInputMode('json')).toBe('json')
      expect(normalizeImportInputMode('text')).toBe('text')
      expect(normalizeImportInputMode('other')).toBe('text')
    })

    it('getImportStatusLabel', () => {
      expect(getImportStatusLabel('running')).toBe('运行中')
      expect(getImportStatusLabel('completed')).toBe('已完成')
      expect(getImportStatusLabel('')).toBe('-')
      expect(getImportStatusLabel('unknown_status')).toBe('unknown_status')
    })

    it('getImportStepLabel', () => {
      expect(getImportStepLabel('splitting')).toBe('分块中')
      expect(getImportStepLabel('')).toBe('-')
    })

    it('getImportStatusVariant', () => {
      expect(getImportStatusVariant('failed')).toBe('destructive')
      expect(getImportStatusVariant('completed')).toBe('default')
      expect(getImportStatusVariant('completed_with_errors')).toBe('secondary')
      expect(getImportStatusVariant('cancelled')).toBe('secondary')
      expect(getImportStatusVariant('running')).toBe('outline')
      expect(getImportStatusVariant('queued')).toBe('outline')
    })

    it('formatImportTime', () => {
      expect(formatImportTime(undefined)).toBe('-')
      expect(formatImportTime(null)).toBe('-')
      expect(formatImportTime(0)).toBe('-')
      expect(formatImportTime(1700000000)).toBeTruthy()
      expect(formatImportTime(1700000000000)).toBeTruthy()
    })
  })

  describe('Delete 格式化函数', () => {
    it('formatDeleteOperationMode', () => {
      expect(formatDeleteOperationMode('entity')).toBe('实体')
      expect(formatDeleteOperationMode('relation')).toBe('关系')
      expect(formatDeleteOperationMode('paragraph')).toBe('段落')
      expect(formatDeleteOperationMode('source')).toBe('来源')
      expect(formatDeleteOperationMode('mixed')).toBe('混合')
      expect(formatDeleteOperationMode('unknown')).toBe('unknown')
      expect(formatDeleteOperationMode('')).toBe('未知')
    })

    it('formatDeleteOperationStatus', () => {
      expect(formatDeleteOperationStatus('executed')).toBe('已执行')
      expect(formatDeleteOperationStatus('restored')).toBe('已恢复')
      expect(formatDeleteOperationStatus('')).toBe('未知')
    })

    it('formatDeleteOperationTime', () => {
      expect(formatDeleteOperationTime(undefined)).toBe('未知时间')
      expect(formatDeleteOperationTime(null)).toBe('未知时间')
      expect(formatDeleteOperationTime(0)).toBe('未知时间')
      expect(formatDeleteOperationTime(1700000000)).toBeTruthy()
    })

    it('trimDeleteItemText', () => {
      expect(trimDeleteItemText('')).toBe('')
      expect(trimDeleteItemText('short text')).toBe('short text')
      expect(trimDeleteItemText('a'.repeat(200), 100)).toHaveLength(103)
      expect(trimDeleteItemText('a'.repeat(200), 100)).toMatch(/\.\.\.$/)
    })

    it('formatDeleteRelationText', () => {
      expect(formatDeleteRelationText('s', 'p', 'o')).toBe('s -> p -> o')
      expect(formatDeleteRelationText('', 'p', 'o')).toBe('p -> o')
      expect(formatDeleteRelationText('', '', '')).toBe('')
    })

    it('getDeleteOperationItemLabel：entity', () => {
      const item = {
        item_type: 'entity',
        item_key: 'key1',
        item_hash: 'hash1',
        payload: { entity: { name: '实体名' } },
      } as never
      expect(getDeleteOperationItemLabel(item)).toBe('实体名')
    })

    it('getDeleteOperationItemLabel：relation', () => {
      const item = {
        item_type: 'relation',
        item_key: 'key1',
        item_hash: 'hash1',
        payload: { relation: { subject: 's', predicate: 'p', object: 'o' } },
      } as never
      expect(getDeleteOperationItemLabel(item)).toBe('s -> p -> o')
    })

    it('getDeleteOperationItemLabel：paragraph', () => {
      const item = {
        item_type: 'paragraph',
        item_key: 'key1',
        item_hash: 'hash1',
        payload: { paragraph: { source: '来源A', content: '内容' } },
      } as never
      expect(getDeleteOperationItemLabel(item)).toBe('来源A')
    })

    it('getDeleteOperationItemPreview：entity 有 paragraph_links', () => {
      const item = {
        item_type: 'entity',
        item_key: 'key1',
        item_hash: 'hash1',
        payload: { paragraph_links: [1, 2, 3] },
      } as never
      expect(getDeleteOperationItemPreview(item)).toBe('关联段落 3 个')
    })

    it('getDeleteOperationItemPreview：entity 无 paragraph_links', () => {
      const item = {
        item_type: 'entity',
        item_key: 'key1',
        item_hash: 'hash1',
        payload: {},
      } as never
      expect(getDeleteOperationItemPreview(item)).toBe('实体快照')
    })

    it('getDeleteOperationItemSource：paragraph', () => {
      const item = {
        item_type: 'paragraph',
        item_key: 'key1',
        item_hash: 'hash1',
        payload: { paragraph: { source: '源' } },
      } as never
      expect(getDeleteOperationItemSource(item)).toBe('源')
    })

    it('getDeleteOperationItemSource：非 paragraph', () => {
      const item = {
        item_type: 'entity',
        item_key: 'key1',
        item_hash: 'hash1',
        payload: { source: '通用源' },
      } as never
      expect(getDeleteOperationItemSource(item)).toBe('通用源')
    })
  })

  describe('Feedback 格式化函数', () => {
    it('formatFeedbackDecision', () => {
      expect(formatFeedbackDecision('correct')).toBe('纠正')
      expect(formatFeedbackDecision('reject')).toBe('否定')
      expect(formatFeedbackDecision('confirm')).toBe('确认')
      expect(formatFeedbackDecision('supplement')).toBe('补充')
      expect(formatFeedbackDecision('none')).toBe('无动作')
      expect(formatFeedbackDecision('')).toBe('未知')
    })

    it('formatFeedbackTaskStatus', () => {
      expect(formatFeedbackTaskStatus('pending')).toBe('待处理')
      expect(formatFeedbackTaskStatus('running')).toBe('处理中')
      expect(formatFeedbackTaskStatus('applied')).toBe('已应用')
      expect(formatFeedbackTaskStatus('skipped')).toBe('已跳过')
      expect(formatFeedbackTaskStatus('error')).toBe('失败')
    })

    it('formatFeedbackRollbackStatus', () => {
      expect(formatFeedbackRollbackStatus('none')).toBe('未回退')
      expect(formatFeedbackRollbackStatus('running')).toBe('回退中')
      expect(formatFeedbackRollbackStatus('rolled_back')).toBe('已回退')
      expect(formatFeedbackRollbackStatus('error')).toBe('回退失败')
    })

    it('getFeedbackStatusVariant', () => {
      expect(getFeedbackStatusVariant('applied')).toBe('default')
      expect(getFeedbackStatusVariant('rolled_back')).toBe('default')
      expect(getFeedbackStatusVariant('error')).toBe('destructive')
      expect(getFeedbackStatusVariant('running')).toBe('outline')
      expect(getFeedbackStatusVariant('pending')).toBe('outline')
      expect(getFeedbackStatusVariant('skipped')).toBe('secondary')
    })

    it('summarizeFeedbackActionPayload：空值', () => {
      expect(summarizeFeedbackActionPayload(undefined)).toBe('')
    })

    it('summarizeFeedbackActionPayload：三元组', () => {
      const result = summarizeFeedbackActionPayload({ subject: 's', predicate: 'p', object: 'o' })
      expect(result).toBe('s -> p -> o')
    })

    it('summarizeFeedbackActionPayload：hash', () => {
      const result = summarizeFeedbackActionPayload({ hash: 'abc123' })
      expect(result).toBe('abc123')
    })

    it('pickFeedbackRelationTriplet：完整三元组', () => {
      const result = pickFeedbackRelationTriplet({ subject: 's', predicate: 'p', object: 'o' })
      expect(result).not.toBeNull()
      expect(result?.subject).toBe('s')
    })

    it('pickFeedbackRelationTriplet：不完整返回 null', () => {
      expect(pickFeedbackRelationTriplet({ subject: 's', predicate: 'p' })).toBeNull()
      expect(pickFeedbackRelationTriplet(null)).toBeNull()
      expect(pickFeedbackRelationTriplet('string')).toBeNull()
    })

    it('formatFeedbackRelationTriplet', () => {
      expect(formatFeedbackRelationTriplet({ subject: 's', predicate: 'p', object: 'o' })).toBe('s -> p -> o')
      expect(formatFeedbackRelationTriplet({ subject: 's' })).toBe('')
    })

    it('getFeedbackCorrectionPreview：null', () => {
      const result = getFeedbackCorrectionPreview(null)
      expect(result.headline).toBe('当前没有纠错摘要')
      expect(result.oldRelation).toBe('')
      expect(result.newRelation).toBe('')
    })

    it('buildFeedbackImpactSummary：null', () => {
      expect(buildFeedbackImpactSummary(null)).toEqual([])
    })

    it('buildFeedbackImpactSummary：有影响计数', () => {
      const task = {
        affected_counts: { relations: 5, corrected_relations: 2 },
      } as never
      const result = buildFeedbackImpactSummary(task)
      expect(result).toContain('影响关系 5 条')
      expect(result).toContain('新增纠正关系 2 条')
    })

    it('formatFeedbackActionType', () => {
      expect(formatFeedbackActionType('classification')).toBe('判定纠错')
      expect(formatFeedbackActionType('forget_relation')).toBe('撤销旧关系')
      expect(formatFeedbackActionType('write_correction')).toBe('写入纠错')
      expect(formatFeedbackActionType('rollback_error')).toBe('回退失败')
      expect(formatFeedbackActionType('')).toBe('未知动作')
    })

    it('describeFeedbackActionLog：classification', () => {
      const item = {
        action_type: 'classification',
        before_payload: undefined,
        after_payload: { subject: 's', predicate: 'p', object: 'o' },
        reason: null,
      } as never
      const result = describeFeedbackActionLog(item)
      expect(result).toContain('系统完成判定')
    })

    it('describeFeedbackActionLog：forget_relation', () => {
      const item = {
        action_type: 'forget_relation',
        before_payload: { hash: 'h1' },
        after_payload: undefined,
        reason: null,
      } as never
      const result = describeFeedbackActionLog(item)
      expect(result).toContain('旧关系已失效')
    })

    it('describeFeedbackActionLog：error 带 reason', () => {
      const item = {
        action_type: 'error',
        before_payload: undefined,
        after_payload: undefined,
        reason: '自定义错误原因',
      } as never
      expect(describeFeedbackActionLog(item)).toBe('自定义错误原因')
    })
  })

  describe('CorrectionTab 零引用验证（spec.md §5.6.1 #7）', () => {
    it('utils 模块无 correction 专属函数', async () => {
      const mod = await import('../utils')
      expect((mod as Record<string, unknown>).useMemoryCorrection).toBeUndefined()
      expect((mod as Record<string, unknown>).CorrectionTab).toBeUndefined()
    })
  })
})