/**
 * useMaisakaMonitor hook 测试
 *
 * 核心验证：
 * - 8 种事件类型分发各一例
 * - message.updated 按 message_id 匹配更新（不新增）
 * - stage.status 按 updatedAt 比较新旧（旧不覆盖新）
 * - 引用计数（多 consumer 挂载/卸载）
 * - 持续获取开关
 * - clearTimeline
 * - StrictMode 竞态
 * - IndexedDB 降级
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { emitEventRef, mockSubscribe, mockUnsubscribe } = vi.hoisted(() => ({
  emitEventRef: { current: (event: unknown) => { void event } },
  mockSubscribe: vi.fn(),
  mockUnsubscribe: vi.fn(async () => {}),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/lib/maisaka-monitor-client', () => ({
  maisakaMonitorClient: {
    subscribe: mockSubscribe,
  },
}))

vi.mock('idb', () => ({
  openDB: vi.fn(),
}))

import type { MaisakaMonitorEvent } from '@/lib/maisaka-monitor-client'

let useMaisakaMonitor: () => import('../hooks/use-maisaka-monitor').UseMaisakaMonitorResult


function emit(event: MaisakaMonitorEvent): void {
  act(() => {
    emitEventRef.current(event)
  })
}

beforeEach(async () => {
  vi.clearAllMocks()
  vi.resetModules()

  mockSubscribe.mockImplementation((listener: (event: unknown) => void) => {
    emitEventRef.current = listener
    return Promise.resolve(mockUnsubscribe)
  })

  const hookModule = await import('../hooks/use-maisaka-monitor')
  useMaisakaMonitor = hookModule.useMaisakaMonitor

  window.localStorage.clear()
  Object.defineProperty(window, 'indexedDB', { value: undefined, configurable: true })
})

describe('useMaisakaMonitor 事件分发', () => {
  it('session.start 事件创建新会话', async () => {
    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    emit({
      type: 'session.start',
      data: { session_id: 'sess-1', session_name: '测试会话', timestamp: 1000 },
    })

    expect(result.current.sessions.get('sess-1')?.sessionName).toBe('测试会话')
  })

  it('stage.status 事件更新阶段状态', async () => {
    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    emit({
      type: 'stage.status',
      data: { session_id: 'sess-1', stage: '思考中', detail: '推理', round_text: '第1轮', agent_state: 'running', stage_started_at: 1000, updated_at: 1000, timestamp: 1000 },
    })

    expect(result.current.stageStatuses.get('sess-1')?.stage).toBe('思考中')
  })

  it('stage.removed 事件删除阶段状态', async () => {
    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    emit({ type: 'stage.status', data: { session_id: 'sess-1', stage: '思考中', detail: '', round_text: '', agent_state: '', stage_started_at: 1000, updated_at: 1000, timestamp: 1000 } })
    emit({ type: 'stage.removed', data: { session_id: 'sess-1', timestamp: 2000 } })

    expect(result.current.stageStatuses.get('sess-1')).toBeUndefined()
  })

  it('stage.snapshot 事件批量应用阶段状态', async () => {
    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    emit({
      type: 'stage.snapshot',
      data: {
        entries: [
          { session_id: 's1', stage: '阶段A', detail: '', round_text: '', agent_state: '', stage_started_at: 1000, updated_at: 1000, timestamp: 1000 },
          { session_id: 's2', stage: '阶段B', detail: '', round_text: '', agent_state: '', stage_started_at: 1000, updated_at: 1000, timestamp: 1000 },
        ],
        timestamp: 1000,
      },
    })

    expect(result.current.stageStatuses.get('s1')?.stage).toBe('阶段A')
    expect(result.current.stageStatuses.get('s2')?.stage).toBe('阶段B')
  })

  it('message.ingested 事件追加时间线条目', async () => {
    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    emit({ type: 'message.ingested', data: { session_id: 'sess-1', speaker_name: '用户', content: '你好', message_id: 'msg-1', timestamp: 1000 } })

    expect(result.current.allTimeline).toHaveLength(1)
    expect(result.current.allTimeline[0].type).toBe('message.ingested')
  })

  it('message.sent 事件追加时间线条目', async () => {
    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    emit({ type: 'message.sent', data: { session_id: 'sess-1', speaker_name: '麦麦', content: '回复', message_id: 'msg-1', timestamp: 1000 } })

    expect(result.current.allTimeline).toHaveLength(1)
    expect(result.current.allTimeline[0].type).toBe('message.sent')
  })

  it('planner.finalized 事件追加时间线条目', async () => {
    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    emit({
      type: 'planner.finalized',
      data: { session_id: 'sess-1', cycle_id: 1, timestamp: 1000, request: null, planner: null, tools: [], final_state: { time_records: {}, agent_state: 'done' } },
    })

    expect(result.current.allTimeline).toHaveLength(1)
    expect(result.current.allTimeline[0].type).toBe('planner.finalized')
  })

  it('message.updated 按 message_id 匹配更新（不新增）', async () => {
    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    emit({ type: 'message.sent', data: { session_id: 'sess-1', speaker_name: '麦麦', content: '原始', message_id: 'msg-1', timestamp: 1000 } })
    emit({ type: 'message.updated', data: { session_id: 'sess-1', speaker_name: '麦麦', content: '更新后', message_id: 'msg-1', timestamp: 2000 } })

    expect(result.current.allTimeline).toHaveLength(1)
    expect((result.current.allTimeline[0].data as { content: string }).content).toBe('更新后')
  })

  it('stage.status 按 updatedAt 比较新旧（旧不覆盖新）', async () => {
    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    emit({ type: 'stage.status', data: { session_id: 'sess-1', stage: '新状态', detail: '', round_text: '', agent_state: '', stage_started_at: 2000, updated_at: 2000, timestamp: 2000 } })
    emit({ type: 'stage.status', data: { session_id: 'sess-1', stage: '旧状态', detail: '', round_text: '', agent_state: '', stage_started_at: 1000, updated_at: 1000, timestamp: 3000 } })

    expect(result.current.stageStatuses.get('sess-1')?.stage).toBe('新状态')
  })
})

describe('useMaisakaMonitor 订阅管理', () => {
  it('多 consumer 挂载/卸载引用计数', async () => {
    const { unmount: unmount1 } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())
    mockSubscribe.mockClear()

    const { unmount: unmount2 } = renderHook(() => useMaisakaMonitor())
    expect(mockSubscribe).not.toHaveBeenCalled()

    unmount1()
    unmount2()
  })

  it('StrictMode 快速卸载/重新挂载仍能接收事件', async () => {
    const { unmount } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    unmount()
    const { result } = renderHook(() => useMaisakaMonitor())

    emit({ type: 'message.ingested', data: { session_id: 'sess-1', speaker_name: '用户', content: '你好', message_id: 'msg-1', timestamp: 1000 } })

    expect(result.current.allTimeline).toHaveLength(1)
  })
})

describe('useMaisakaMonitor 操作', () => {
  it('持续获取开关 setBackgroundCollectionEnabled', async () => {
    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    act(() => {
      result.current.setBackgroundCollectionEnabled(true)
    })

    expect(result.current.backgroundCollection).toBe(true)
    expect(window.localStorage.getItem('maisaka-monitor-background-collection')).toBe('true')
  })

  it('clearTimeline 清空时间线和会话', async () => {
    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    emit({ type: 'message.ingested', data: { session_id: 'sess-1', speaker_name: '用户', content: '你好', message_id: 'msg-1', timestamp: 1000 } })
    expect(result.current.allTimeline).toHaveLength(1)

    act(() => {
      result.current.clearTimeline()
    })

    expect(result.current.allTimeline).toHaveLength(0)
    expect(result.current.sessions.size).toBe(0)
  })

  it('IndexedDB 不可用时降级为纯内存模式', async () => {
    expect(window.indexedDB).toBeUndefined()

    const { result } = renderHook(() => useMaisakaMonitor())
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled())

    emit({ type: 'message.ingested', data: { session_id: 'sess-1', speaker_name: '用户', content: '你好', message_id: 'msg-1', timestamp: 1000 } })

    expect(result.current.allTimeline).toHaveLength(1)
  })
})
