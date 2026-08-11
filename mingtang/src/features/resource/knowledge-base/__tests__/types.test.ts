/**
 * types.ts 类型定义测试（R4-2-1 测试先行）
 *
 * 核心验证：
 * - KnowledgeBaseTab 仅 4 值（砍 correction/graph/timeline/episodes/profiles/maintenance）
 * - KnowledgeBaseDeepLinkState 字段正确性（tab 必填 + taskId/operationId/source 可选——不含 correction 参数）
 * - CorrectionTab 零引用验证（spec.md §5.6.1 #3）
 */
import { describe, expect, it } from 'vitest'

import {
  KNOWLEDGE_BASE_TABS,
  type KnowledgeBaseDeepLinkState,
  type KnowledgeBaseTab,
} from '../types'

describe('R4-2-1 types.ts 类型定义', () => {
  describe('KnowledgeBaseTab 4 tab 联合类型', () => {
    it('KNOWLEDGE_BASE_TABS 恰好 4 个 tab', () => {
      expect(KNOWLEDGE_BASE_TABS).toHaveLength(4)
    })

    it('包含 import/tuning/delete/feedback', () => {
      expect(KNOWLEDGE_BASE_TABS).toContain('import')
      expect(KNOWLEDGE_BASE_TABS).toContain('tuning')
      expect(KNOWLEDGE_BASE_TABS).toContain('delete')
      expect(KNOWLEDGE_BASE_TABS).toContain('feedback')
    })

    it('不含 correction（spec.md §5.6.1 #5 砍 correction tab 入口）', () => {
      expect(KNOWLEDGE_BASE_TABS).not.toContain('correction')
    })

    it('不含 graph/timeline/episodes/profiles/maintenance（spec.md §5.1.1 #8 禁止 5 tabs）', () => {
      expect(KNOWLEDGE_BASE_TABS).not.toContain('graph')
      expect(KNOWLEDGE_BASE_TABS).not.toContain('timeline')
      expect(KNOWLEDGE_BASE_TABS).not.toContain('episodes')
      expect(KNOWLEDGE_BASE_TABS).not.toContain('profiles')
      expect(KNOWLEDGE_BASE_TABS).not.toContain('maintenance')
    })

    it('KNOWLEDGE_BASE_TABS 类型为 KnowledgeBaseTab[]（satisfies 检查）', () => {
      for (const tab of KNOWLEDGE_BASE_TABS) {
        expect(['import', 'tuning', 'delete', 'feedback']).toContain(tab)
      }
    })
  })

  describe('KnowledgeBaseDeepLinkState 深链接状态', () => {
    it('tab 必填字段可正确构造', () => {
      const state: KnowledgeBaseDeepLinkState = { tab: 'import' }
      expect(state.tab).toBe('import')
    })

    it('taskId 可选字段（feedback 任务 ID）', () => {
      const state: KnowledgeBaseDeepLinkState = { tab: 'feedback', taskId: 42 }
      expect(state.taskId).toBe(42)
    })

    it('operationId 可选字段（delete 操作 ID）', () => {
      const state: KnowledgeBaseDeepLinkState = { tab: 'delete', operationId: 'op-001' }
      expect(state.operationId).toBe('op-001')
    })

    it('source 可选字段（delete 来源搜索）', () => {
      const state: KnowledgeBaseDeepLinkState = { tab: 'delete', source: 'group_123' }
      expect(state.source).toBe('group_123')
    })

    it('可同时携带所有可选字段', () => {
      const state: KnowledgeBaseDeepLinkState = {
        tab: 'delete',
        taskId: 1,
        operationId: 'op-002',
        source: 'group_456',
      }
      expect(state.tab).toBe('delete')
      expect(state.taskId).toBe(1)
      expect(state.operationId).toBe('op-002')
      expect(state.source).toBe('group_456')
    })

    it('不含 correction 参数（spec.md §5.6.1 #3 砍 correction 路由参数）', () => {
      const state: KnowledgeBaseDeepLinkState = { tab: 'feedback' }
      expect(state).not.toHaveProperty('planId')
      expect(state).not.toHaveProperty('personId')
      expect(state).not.toHaveProperty('correctionPlanId')
    })
  })

  describe('CorrectionTab 零引用验证（spec.md §5.6.1）', () => {
    it('KnowledgeBaseTab 类型不含 correction', () => {
      const validTabs: KnowledgeBaseTab[] = ['import', 'tuning', 'delete', 'feedback']
      expect(validTabs).not.toContain('correction')
    })

    it('KNOWLEDGE_BASE_TABS 运行时常量不含 correction', () => {
      expect(KNOWLEDGE_BASE_TABS.some((t) => (t as string) === 'correction')).toBe(false)
    })
  })
})