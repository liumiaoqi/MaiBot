import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import type { ChatRuntimeStatus, ChatTab, MessageSegment, WsMessage } from '../types'
import { VIRTUAL_TABS_STORAGE_KEY } from '../types'
import {
  deduplicateMessage,
  generateUserId,
  getChatTabDisplayName,
  getOrCreateUserId,
  getSavedVirtualTabs,
  getStoredUserName,
  matchesMonitorTarget,
  resolveStatusKind,
  saveUserName,
  saveVirtualTabs,
} from '../utils'

// ─── types.ts ────────────────────────────────────────────────────

describe('chat types', () => {
  it('MessageSegment 涵盖 12 种段类型', () => {
    const segmentTypes = [
      'text',
      'image',
      'emoji',
      'face',
      'voice',
      'video',
      'music',
      'file',
      'reply',
      'at',
      'forward',
      'unknown',
    ] as const
    const segments: MessageSegment[] = segmentTypes.map((type) => ({ type, data: '' }))
    expect(segments).toHaveLength(12)
    // 每个段类型可构造且保留
    expect(segments.map((s) => s.type)).toEqual(segmentTypes)
  })

  it('WsMessage 携带 8 种消息类型字段', () => {
    const wsTypes = [
      'session_info',
      'system',
      'user_message',
      'bot_message',
      'typing',
      'error',
      'history',
      'bot_typing',
    ] as const
    const messages: WsMessage[] = wsTypes.map((type) => ({ type }))
    expect(messages).toHaveLength(8)
  })

  it('ChatTab 包含 webui 与 virtual 两种类型', () => {
    const webuiTab: ChatTab = {
      id: 'webui-default',
      type: 'webui',
      label: 'WebUI',
      messages: [],
      isConnected: true,
      isTyping: false,
      sessionInfo: {},
    }
    const virtualTab: ChatTab = {
      id: 'v1',
      type: 'virtual',
      label: '虚拟会话',
      messages: [],
      isConnected: false,
      isTyping: false,
      sessionInfo: {},
      virtualConfig: {
        platform: 'qq',
        personId: 'p1',
        userId: 'u1',
        userName: '虚拟用户',
        groupName: '虚拟群',
        groupId: 'g1',
      },
    }
    expect(webuiTab.type).toBe('webui')
    expect(virtualTab.type).toBe('virtual')
    expect(virtualTab.virtualConfig?.platform).toBe('qq')
  })

  it('ChatRuntimeStatus 覆盖五种运行状态', () => {
    const statuses: ChatRuntimeStatus[] = ['idle', 'thinking', 'typing', 'acting', 'error']
    expect(statuses).toHaveLength(5)
  })
})

// ─── utils.ts：localStorage 工具 ─────────────────────────────────

describe('chat utils localStorage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('generateUserId 生成 webui_ 前缀唯一 ID', () => {
    const id1 = generateUserId()
    const id2 = generateUserId()
    expect(id1).toMatch(/^webui_/)
    expect(id2).toMatch(/^webui_/)
    expect(id1).not.toBe(id2)
  })

  it('getOrCreateUserId 首次生成并持久化，二次读取同值', () => {
    const first = getOrCreateUserId()
    const second = getOrCreateUserId()
    expect(first).toBe(second)
    expect(localStorage.getItem('maibot_webui_user_id')).toBe(first)
  })

  it('getStoredUserName 无存储时回退默认昵称', () => {
    expect(getStoredUserName()).toBe('WebUI用户')
  })

  it('saveUserName 写入后 getStoredUserName 读取一致', () => {
    saveUserName('小明')
    expect(getStoredUserName()).toBe('小明')
  })

  it('saveVirtualTabs / getSavedVirtualTabs 往返一致', () => {
    const tabs = [
      {
        id: 'v1',
        label: '虚拟A',
        virtualConfig: {
          platform: 'qq',
          personId: 'p1',
          userId: 'u1',
          userName: 'A',
          groupName: 'G',
          groupId: 'g1',
        },
        createdAt: 1,
      },
    ]
    saveVirtualTabs(tabs)
    const loaded = getSavedVirtualTabs()
    expect(loaded).toEqual(tabs)
  })

  it('getSavedVirtualTabs 解析失败时回退空数组且不抛异常', () => {
    localStorage.setItem(VIRTUAL_TABS_STORAGE_KEY, '{bad json')
    expect(getSavedVirtualTabs()).toEqual([])
  })

  it('getChatTabDisplayName：virtual 用 label，webui 用 bot_name', () => {
    const virtualTab: ChatTab = {
      id: 'v1',
      type: 'virtual',
      label: '虚拟标签',
      messages: [],
      isConnected: true,
      isTyping: false,
      sessionInfo: {},
    }
    const webuiTab: ChatTab = {
      id: 'webui-default',
      type: 'webui',
      label: 'WebUI',
      messages: [],
      isConnected: true,
      isTyping: false,
      sessionInfo: { bot_name: '麦麦' },
    }
    expect(getChatTabDisplayName(virtualTab, 'fallback')).toBe('虚拟标签')
    expect(getChatTabDisplayName(webuiTab, 'fallback')).toBe('麦麦')
  })

  it('getChatTabDisplayName：webui 无 bot_name 时回退', () => {
    const webuiTab: ChatTab = {
      id: 'webui-default',
      type: 'webui',
      label: 'WebUI',
      messages: [],
      isConnected: true,
      isTyping: false,
      sessionInfo: {},
    }
    expect(getChatTabDisplayName(webuiTab, '麦麦')).toBe('麦麦')
  })
})

// ─── utils.ts：resolveStatusKind ─────────────────────────────────

describe('resolveStatusKind', () => {
  it('think / reason 关键词推断为 thinking', () => {
    expect(resolveStatusKind('thinking', '')).toBe('thinking')
    expect(resolveStatusKind('reasoning', '')).toBe('thinking')
    expect(resolveStatusKind('llm_think', '')).toBe('thinking')
  })

  it('typ / generat / writ 关键词推断为 typing', () => {
    expect(resolveStatusKind('typing', '')).toBe('typing')
    expect(resolveStatusKind('generate_response', '')).toBe('typing')
    expect(resolveStatusKind('write_text', '')).toBe('typing')
  })

  it('act / tool / execut / action 关键词推断为 acting', () => {
    expect(resolveStatusKind('acting', '')).toBe('acting')
    expect(resolveStatusKind('tool_call', '')).toBe('acting')
    expect(resolveStatusKind('execute_action', '')).toBe('acting')
  })

  it('error / fail 关键词推断为 error', () => {
    expect(resolveStatusKind('error', '')).toBe('error')
    expect(resolveStatusKind('llm_failed', '')).toBe('error')
  })

  it('未知 stage 回退 idle', () => {
    expect(resolveStatusKind('idle', '')).toBe('idle')
    expect(resolveStatusKind('unknown_stage', '')).toBe('idle')
  })

  it('大小写不敏感', () => {
    expect(resolveStatusKind('THINKING', '')).toBe('thinking')
    expect(resolveStatusKind('ToolCall', '')).toBe('acting')
  })
})

// ─── utils.ts：matchesMonitorTarget ──────────────────────────────

describe('matchesMonitorTarget', () => {
  const baseTab: ChatTab = {
    id: 'tab-1',
    type: 'webui',
    label: '测试会话',
    messages: [],
    isConnected: true,
    isTyping: false,
    sessionInfo: { session_id: 'sess-123' },
  }

  it('一级匹配：session_id 精确命中', () => {
    expect(
      matchesMonitorTarget({ session_id: 'sess-123' }, baseTab)
    ).toBe(true)
  })

  it('一级未命中时二级匹配：session_name 命中 label', () => {
    expect(
      matchesMonitorTarget({ session_id: 'other', session_name: '测试会话' }, baseTab)
    ).toBe(true)
  })

  it('一二级未命中时三级匹配：platform 命中 virtualConfig.platform', () => {
    const virtualTab: ChatTab = {
      id: 'v1',
      type: 'virtual',
      label: '虚拟',
      messages: [],
      isConnected: true,
      isTyping: false,
      sessionInfo: {},
      virtualConfig: {
        platform: 'qq',
        personId: 'p1',
        userId: 'u1',
        userName: 'U',
        groupName: 'G',
        groupId: 'g1',
      },
    }
    expect(
      matchesMonitorTarget({ session_id: 'other', session_name: 'no', platform: 'qq' }, virtualTab)
    ).toBe(true)
  })

  it('全部未命中返回 false', () => {
    expect(
      matchesMonitorTarget({ session_id: 'other', session_name: 'no', platform: 'wx' }, baseTab)
    ).toBe(false)
  })

  it('空事件不命中', () => {
    expect(matchesMonitorTarget({}, baseTab)).toBe(false)
  })
})

// ─── utils.ts：deduplicateMessage ────────────────────────────────

describe('deduplicateMessage', () => {
  it('首次出现的 hash 不重复且加入集合', () => {
    const result = deduplicateMessage(new Set(), 'user-hello-1000', 100)
    expect(result.isDuplicate).toBe(false)
    expect(result.updatedSet.has('user-hello-1000')).toBe(true)
  })

  it('已存在的 hash 判定为重复', () => {
    const existing = new Set(['user-hello-1000'])
    const result = deduplicateMessage(existing, 'user-hello-1000', 100)
    expect(result.isDuplicate).toBe(true)
  })

  it('超过上限时淘汰最早插入的 hash', () => {
    const initial = new Set<string>()
    for (let i = 0; i < 100; i++) {
      initial.add(`hash-${i}`)
    }
    // 插入第 101 条，最早 hash-0 应被淘汰
    const result = deduplicateMessage(initial, 'hash-100', 100)
    expect(result.isDuplicate).toBe(false)
    expect(result.updatedSet.size).toBe(100)
    expect(result.updatedSet.has('hash-0')).toBe(false)
    expect(result.updatedSet.has('hash-100')).toBe(true)
  })

  it('默认上限 100', () => {
    const initial = new Set<string>()
    for (let i = 0; i < 100; i++) {
      initial.add(`h-${i}`)
    }
    const result = deduplicateMessage(initial, 'h-new')
    expect(result.updatedSet.size).toBe(100)
    expect(result.updatedSet.has('h-0')).toBe(false)
  })

  it('user 与 bot hash 互不干扰', () => {
    const set = new Set<string>()
    const r1 = deduplicateMessage(set, 'user-hello-1000', 100)
    const r2 = deduplicateMessage(r1.updatedSet, 'bot-hello-1000', 100)
    expect(r1.isDuplicate).toBe(false)
    expect(r2.isDuplicate).toBe(false)
  })
})