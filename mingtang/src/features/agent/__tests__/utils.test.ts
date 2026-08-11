import { describe, expect, it } from 'vitest'
import type { AgentConfigInfo, BatchEmotionItem, BatchRelationshipItem, BatchLatestSubAgentItem, InternalRelationshipSummaryItem } from '@/lib/agent-api'
import { deriveActivityRhythmData, deriveEmotionPulseData, deriveInnerActivityData, deriveRelationshipWarmthData, deriveVitalSignsData } from '../utils/vital-signs'
import { deriveConstellationData } from '../utils/constellation'
import { EMOTION_COLORS, EMOTION_ICONS } from '../utils/emotion-constants'

function makeAgent(overrides: Partial<AgentConfigInfo> = {}): AgentConfigInfo {
  return {
    agent_id: 'agent-1',
    display_name: '测试智能体',
    personality: '',
    reply_style: '',
    is_default: false,
    color: '#9b59b6',
    emotion_baseline: {},
    emotion_decay_rate: 0.5,
    relationship_growth_rate: 0.5,
    talk_value_modifier: 1.0,
    memory_focus_areas: [],
    internal_relationships: [],
    anti_mechanization_rules: [],
    ...overrides,
  }
}

function makeEmotion(overrides: Partial<BatchEmotionItem> = {}): BatchEmotionItem {
  return {
    emotions: { calm: 0.8, happy: 0.2 },
    dominant_emotion: 'calm',
    dominant_emotion_label: '平静',
    emotion_labels: { calm: '平静', happy: '开心' },
    ...overrides,
  }
}

describe('deriveEmotionPulseData', () => {
  it('空数据返回 null', () => {
    expect(deriveEmotionPulseData(null)).toBeNull()
    expect(deriveEmotionPulseData(undefined)).toBeNull()
  })

  it('提取主导情绪与最大强度', () => {
    const pulse = deriveEmotionPulseData(makeEmotion())
    expect(pulse?.dominantEmotion).toBe('calm')
    expect(pulse?.dominantEmotionLabel).toBe('平静')
    expect(pulse?.intensity).toBe(0.8)
  })

  it('色板取 EMOTION_COLORS，未知情绪回退默认色', () => {
    const known = deriveEmotionPulseData(makeEmotion({ dominant_emotion: 'happy' }))
    expect(known?.color).toBe(EMOTION_COLORS.happy)
    const unknown = deriveEmotionPulseData(makeEmotion({ dominant_emotion: 'unknown' }))
    expect(unknown?.color).toBe('#9b59b6')
  })
})

describe('deriveActivityRhythmData', () => {
  it('高活跃（session>0 且 modifier>1.0）→ active', () => {
    const agent = makeAgent({ talk_value_modifier: 1.2 })
    expect(deriveActivityRhythmData(agent, 3)).toEqual({ status: 'active', sessionCount: 3 })
  })

  it('中等（session>0 且 modifier>=0.5）→ quiet', () => {
    const agent = makeAgent({ talk_value_modifier: 0.8 })
    expect(deriveActivityRhythmData(agent, 2)).toEqual({ status: 'quiet', sessionCount: 2 })
  })

  it('无会话或低 modifier → dormant', () => {
    const agent = makeAgent({ talk_value_modifier: 1.2 })
    expect(deriveActivityRhythmData(agent, 0)).toEqual({ status: 'dormant', sessionCount: 0 })
    const lowAgent = makeAgent({ talk_value_modifier: 0.3 })
    expect(deriveActivityRhythmData(lowAgent, 5)).toEqual({ status: 'dormant', sessionCount: 5 })
  })
})

describe('deriveRelationshipWarmthData', () => {
  it('用户关系存在时按最高等级定温暖度', () => {
    const relationships: BatchRelationshipItem[] = [
      { user_id: 'u1', level: 3, level_name: '密友', score: 80, total_interactions: 10 },
      { user_id: 'u2', level: 1, level_name: '相识', score: 30, total_interactions: 2 },
    ]
    const result = deriveRelationshipWarmthData(relationships, [])
    expect(result.warmth).toBe('warm')
    expect(result.relationshipCount).toBe(2)
    expect(result.highestLevel).toBe(3)
    expect(result.dataSource).toBe('user_relationship')
  })

  it('无用户关系时按内部关系平均提及度', () => {
    const internal: InternalRelationshipSummaryItem[] = [
      { target_agent_id: 'a2', relationship_type: 'friend', mention_tendency: 0.6 },
      { target_agent_id: 'a3', relationship_type: 'rival', mention_tendency: 0.4 },
    ]
    const result = deriveRelationshipWarmthData(null, internal)
    expect(result.warmth).toBe('moderate')
    expect(result.dataSource).toBe('internal_relationship')
  })

  it('都无数据 → no_data', () => {
    const result = deriveRelationshipWarmthData(null, null)
    expect(result).toEqual({ warmth: 'no_data', relationshipCount: 0, highestLevel: 0, dataSource: 'none' })
  })
})

describe('deriveInnerActivityData', () => {
  it('无记录 → unavailable', () => {
    expect(deriveInnerActivityData(null)).toEqual({ status: 'unavailable', latestType: null, latestSummary: null })
  })

  it('一小时内完成 → introspecting', () => {
    const record: BatchLatestSubAgentItem = {
      id: 1,
      subagent_id: 's1',
      agent_id: 'agent-1',
      subagent_type: 'self_reflection',
      status: 'completed',
      completed_at: new Date(Date.now() - 60 * 1000).toISOString(),
      result_summary: '进行了内省',
    }
    const result = deriveInnerActivityData(record)
    expect(result.status).toBe('introspecting')
    expect(result.latestType).toBe('self_reflection')
    expect(result.latestSummary).toBe('进行了内省')
  })

  it('超过一小时 → quiet', () => {
    const record: BatchLatestSubAgentItem = {
      id: 2,
      subagent_id: 's2',
      agent_id: 'agent-1',
      subagent_type: 'self_reflection',
      status: 'completed',
      completed_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      result_summary: '旧记录',
    }
    expect(deriveInnerActivityData(record).status).toBe('quiet')
  })

  it('completed_at 为空 → quiet', () => {
    const record: BatchLatestSubAgentItem = {
      id: 3,
      subagent_id: 's3',
      agent_id: 'agent-1',
      subagent_type: 'task',
      status: 'running',
      completed_at: null,
      result_summary: '',
    }
    expect(deriveInnerActivityData(record).status).toBe('quiet')
  })
})

describe('deriveVitalSignsData', () => {
  it('聚合全部派生结果', () => {
    const agent = makeAgent({ talk_value_modifier: 1.5 })
    const result = deriveVitalSignsData(agent, makeEmotion(), [], 2, null, [])
    expect(result.agentId).toBe('agent-1')
    expect(result.displayName).toBe('测试智能体')
    expect(result.color).toBe('#9b59b6')
    expect(result.activityRhythm.status).toBe('active')
    expect(result.emotionPulse?.dominantEmotion).toBe('calm')
    expect(result.relationshipWarmth.dataSource).toBe('none')
    expect(result.innerActivity.status).toBe('unavailable')
  })
})

describe('deriveConstellationData', () => {
  it('生成节点（含默认情绪 label 回退）', () => {
    const agents = [makeAgent({ internal_relationships: [] })]
    const result = deriveConstellationData(agents, {}, {})
    expect(result.nodes).toHaveLength(1)
    expect(result.nodes[0].activityStatus).toBe('dormant')
    expect(result.nodes[0].dominantEmotion).toBe('calm')
    expect(result.nodes[0].dominantEmotionLabel).toBe('平静')
  })

  it('生成边并去重（双向关系只建一条）', () => {
    const agents: AgentConfigInfo[] = [
      makeAgent({
        agent_id: 'a1',
        internal_relationships: [{ target_agent_id: 'a2', relationship_type: 'friend', attitude: 'positive', interaction_style: 'warm', anti_mechanization: '', mention_tendency: 0.8 }],
      }),
      makeAgent({
        agent_id: 'a2',
        internal_relationships: [{ target_agent_id: 'a1', relationship_type: 'friend', attitude: 'positive', interaction_style: 'warm', anti_mechanization: '', mention_tendency: 0.7 }],
      }),
    ]
    const result = deriveConstellationData(agents, {}, {})
    expect(result.edges).toHaveLength(1)
    expect(result.edges[0].source).toBe('a1')
    expect(result.edges[0].target).toBe('a2')
    expect(result.edges[0].mentionLabel).toBe('close')
    expect(result.edges[0].width).toBe(4)
  })

  it('忽略指向不存在智能体的边', () => {
    const agents: AgentConfigInfo[] = [
      makeAgent({
        agent_id: 'a1',
        internal_relationships: [{ target_agent_id: 'ghost', relationship_type: 'rival', attitude: 'negative', interaction_style: 'cold', anti_mechanization: '', mention_tendency: 0.5 }],
      }),
    ]
    const result = deriveConstellationData(agents, {}, {})
    expect(result.edges).toHaveLength(0)
  })
})

describe('emotion-constants', () => {
  it('EMOTION_COLORS 与 EMOTION_ICONS key 集合一致', () => {
    expect(Object.keys(EMOTION_COLORS).sort()).toEqual(Object.keys(EMOTION_ICONS).sort())
  })

  it('已知情绪均有色值与图标', () => {
    for (const emotion of ['happy', 'sad', 'anxious', 'angry', 'calm', 'excited', 'lonely']) {
      expect(EMOTION_COLORS[emotion]).toMatch(/^#[0-9a-f]{6}$/)
      expect(EMOTION_ICONS[emotion]).toBeTruthy()
    }
  })
})