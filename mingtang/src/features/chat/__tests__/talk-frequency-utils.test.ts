/**
 * talk-frequency 工具函数 + 组件测试（R3-2-2 测试先行）
 */
import { describe, expect, it } from 'vitest'

import type { ChatStreamDetail } from '@/lib/chat-management-api'

import {
  clampTalkFrequencyValue,
  DAY_MINUTES,
  formatFrequencySummary,
  formatTimelineMinute,
  formatTalkTimeRange,
  getExactTalkRules,
  getTimelineSegments,
  parseTimelineMinute,
  parseTalkTimeRange,
  talkValueColor,
  TIMELINE_DRAG_STEP_MINUTES,
  TIMELINE_TICKS,
} from '../components/talk-frequency-utils'

/** 构造测试用 ChatStreamDetail */
function makeDetail(overrides: Partial<ChatStreamDetail> = {}): ChatStreamDetail {
  return {
    session_id: 'session-1',
    platform: 'qq',
    target_id: 'target-1',
    chat_type: 'group',
    display_name: '测试群',
    group_id: 'group-1',
    user_id: null,
    expression: { use: true, learn: false, matched_rule: null },
    jargon: { use: true, learn: false, matched_rule: null },
    talk_frequency: {
      enabled: true,
      base_value: 0.5,
      base_value_label: '0.50',
      effective_value: 0.5,
      effective_value_label: '0.50',
      current_time: '12:00',
      matched_rules: [],
    },
    prompts: {
      base_prompt_type: 'group',
      base_prompt_title: '',
      base_prompt: '',
      chat_prompts: [],
    },
    ...overrides,
  }
}

describe('常量', () => {
  it('DAY_MINUTES = 1440', () => {
    expect(DAY_MINUTES).toBe(1440)
  })

  it('TIMELINE_TICKS 9 个刻度', () => {
    expect(TIMELINE_TICKS).toHaveLength(9)
    expect(TIMELINE_TICKS[0]).toBe(0)
    expect(TIMELINE_TICKS[8]).toBe(24)
  })

  it('TIMELINE_DRAG_STEP_MINUTES = 5', () => {
    expect(TIMELINE_DRAG_STEP_MINUTES).toBe(5)
  })
})

describe('clampTalkFrequencyValue', () => {
  it('正常值不变', () => {
    expect(clampTalkFrequencyValue(0.5)).toBe(0.5)
  })

  it('负数钳为 0', () => {
    expect(clampTalkFrequencyValue(-1)).toBe(0)
  })

  it('超 1 钳为 1', () => {
    expect(clampTalkFrequencyValue(2)).toBe(1)
  })

  it('NaN 返回 0', () => {
    expect(clampTalkFrequencyValue(Number.NaN)).toBe(0)
  })

  it('Infinity 返回 0', () => {
    expect(clampTalkFrequencyValue(Number.POSITIVE_INFINITY)).toBe(0)
  })
})

describe('parseTimelineMinute', () => {
  it('有效 HH:MM 返回分钟', () => {
    expect(parseTimelineMinute('00:00')).toBe(0)
    expect(parseTimelineMinute('12:30')).toBe(750)
    expect(parseTimelineMinute('23:59')).toBe(1439)
  })

  it('无效格式返回 null', () => {
    expect(parseTimelineMinute('abc')).toBeNull()
    expect(parseTimelineMinute('25:00')).toBeNull()
    expect(parseTimelineMinute('12:60')).toBeNull()
    expect(parseTimelineMinute('')).toBeNull()
  })
})

describe('formatTimelineMinute', () => {
  it('分钟转 HH:MM', () => {
    expect(formatTimelineMinute(0)).toBe('00:00')
    expect(formatTimelineMinute(750)).toBe('12:30')
    expect(formatTimelineMinute(1439)).toBe('23:59')
  })

  it('超范围钳制', () => {
    expect(formatTimelineMinute(-1)).toBe('00:00')
    expect(formatTimelineMinute(1440)).toBe('23:59')
  })

  it('四舍五入', () => {
    expect(formatTimelineMinute(750.4)).toBe('12:30')
    expect(formatTimelineMinute(750.5)).toBe('12:31')
  })
})

describe('parseTalkTimeRange', () => {
  it('空字符串返回全天', () => {
    expect(parseTalkTimeRange('')).toEqual({ start: 0, end: 1439 })
  })

  it('* 返回全天', () => {
    expect(parseTalkTimeRange('*')).toEqual({ start: 0, end: 1439 })
  })

  it('HH:MM-HH:MM 解析', () => {
    expect(parseTalkTimeRange('09:00-17:00')).toEqual({ start: 540, end: 1020 })
  })

  it('无效格式返回 null', () => {
    expect(parseTalkTimeRange('abc')).toBeNull()
    expect(parseTalkTimeRange('09:00-17:00-20:00')).toBeNull()
  })
})

describe('formatTalkTimeRange', () => {
  it('范围转字符串', () => {
    expect(formatTalkTimeRange({ start: 540, end: 1020 })).toBe('09:00-17:00')
  })
})

describe('getTimelineSegments', () => {
  it('正常范围单段', () => {
    const segments = getTimelineSegments({ start: 540, end: 1020 })
    expect(segments).toHaveLength(1)
    expect(segments[0].left).toBeCloseTo(37.5, 1)
    expect(segments[0].width).toBeCloseTo(33.4, 1)
  })

  it('跨午夜两段', () => {
    const segments = getTimelineSegments({ start: 1200, end: 300 })
    expect(segments).toHaveLength(2)
    expect(segments[0].left).toBeCloseTo(83.3, 1)
    expect(segments[1].left).toBe(0)
  })
})

describe('talkValueColor', () => {
  it('>=0.75 返回 emerald', () => {
    expect(talkValueColor(0.75)).toBe('bg-emerald-500')
    expect(talkValueColor(0.8)).toBe('bg-emerald-500')
  })

  it('>=0.45 返回 amber', () => {
    expect(talkValueColor(0.45)).toBe('bg-amber-500')
    expect(talkValueColor(0.5)).toBe('bg-amber-500')
  })

  it('<0.45 返回 sky', () => {
    expect(talkValueColor(0.3)).toBe('bg-sky-500')
    expect(talkValueColor(0)).toBe('bg-sky-500')
  })
})

describe('formatFrequencySummary', () => {
  it('数字字符串保留两位小数', () => {
    expect(formatFrequencySummary('0.5')).toBe('0.50')
    expect(formatFrequencySummary('1')).toBe('1.00')
  })

  it('非数字字符串原样返回', () => {
    expect(formatFrequencySummary('abc')).toBe('abc')
  })
})

describe('getExactTalkRules', () => {
  it('提取匹配当前聊天流的精确规则', () => {
    const detail = makeDetail({
      talk_frequency: {
        enabled: true,
        base_value: 0.5,
        base_value_label: '0.50',
        effective_value: 0.5,
        effective_value_label: '0.50',
        current_time: '12:00',
        matched_rules: [
          { platform: 'qq', item_id: 'target-1', type: 'group', time: '*', value: 0.5, value_label: '0.50', target_priority: 1, time_priority: 0, is_effective: true, time_active: true, is_default_target: false },
          { platform: 'wx', item_id: 'target-2', type: 'group', time: '*', value: 0.3, value_label: '0.30', target_priority: 1, time_priority: 0, is_effective: false, time_active: true, is_default_target: false },
        ],
      },
    })
    const exact = getExactTalkRules(detail)
    expect(exact).toHaveLength(1)
    expect(exact[0].platform).toBe('qq')
  })

  it('无匹配返回空数组', () => {
    const detail = makeDetail()
    expect(getExactTalkRules(detail)).toHaveLength(0)
  })
})