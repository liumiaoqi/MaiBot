/**
 * MaisakaMonitorPage 页面组件测试
 *
 * 核心验证：
 * - 三栏布局渲染（侧边栏 + 阶段面板 + 时间线）
 * - 空状态（侧边栏占位 + 阶段面板占位 + 时间线空）
 * - 会话切换 / 清空 / 折叠
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/lib/avatar-url', () => ({
  useResolvedAvatarUrl: () => undefined,
}))

vi.mock('../components/timeline-entry-item', () => ({
  TimelineEntryItem: () => null,
  formatRelativeTime: () => ({ key: 'monitor.maisaka.justNow' }),
  formatMs: () => '0ms',
  formatTimestamp: () => '00:00:00',
}))

const mockUseMaisakaMonitor = vi.hoisted(() => vi.fn())

vi.mock('../hooks/use-maisaka-monitor', () => ({
  useMaisakaMonitor: mockUseMaisakaMonitor,
}))

import { MaisakaMonitorPage } from '../index'
import type { UseMaisakaMonitorResult } from '../hooks/use-maisaka-monitor'

function makeResult(overrides: Partial<UseMaisakaMonitorResult> = {}): UseMaisakaMonitorResult {
  return {
    timeline: [],
    allTimeline: [],
    sessions: new Map(),
    stageStatuses: new Map(),
    selectedSession: null,
    setSelectedSession: vi.fn(),
    connected: false,
    backgroundCollection: false,
    setBackgroundCollectionEnabled: vi.fn(),
    clearTimeline: vi.fn(),
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseMaisakaMonitor.mockReturnValue(makeResult())
  window.localStorage.clear()
})

describe('MaisakaMonitorPage', () => {
  it('PageShell 渲染 + 标题', () => {
    render(<MaisakaMonitorPage />)
    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    expect(screen.getByText('monitor.maisaka.title')).toBeInTheDocument()
  })

  it('默认折叠态不显示侧边栏会话名', () => {
    render(<MaisakaMonitorPage />)
    // 折叠态：侧边栏标题文字隐藏（text-[0px]），但按钮可见
    expect(screen.getByTitle('monitor.maisaka.expandSidebar')).toBeInTheDocument()
  })

  it('展开态空状态：侧边栏占位 + 阶段面板占位 + 时间线空', () => {
    window.localStorage.setItem('maisaka-monitor-sidebar-collapsed', 'false')
    render(<MaisakaMonitorPage />)
    expect(screen.getByText('monitor.maisaka.waitingSession')).toBeInTheDocument()
    expect(screen.getByText('monitor.maisaka.noStageStatus')).toBeInTheDocument()
    expect(screen.getByText('monitor.maisaka.waitingEvents')).toBeInTheDocument()
  })

  it('点击折叠按钮切换侧边栏', () => {
    window.localStorage.setItem('maisaka-monitor-sidebar-collapsed', 'false')
    render(<MaisakaMonitorPage />)
    const collapseBtn = screen.getByTitle('monitor.maisaka.collapseSidebar')
    fireEvent.click(collapseBtn)
    expect(screen.getByTitle('monitor.maisaka.expandSidebar')).toBeInTheDocument()
  })

  it('清空按钮调用 clearTimeline', () => {
    const clearTimeline = vi.fn()
    mockUseMaisakaMonitor.mockReturnValue(makeResult({ clearTimeline }))
    render(<MaisakaMonitorPage />)
    fireEvent.click(screen.getByLabelText('monitor.maisaka.clear'))
    expect(clearTimeline).toHaveBeenCalledOnce()
  })

  it('点击会话调用 setSelectedSession', () => {
    const setSelectedSession = vi.fn()
    const sessions = new Map([
      ['s1', { sessionId: 's1', sessionName: '测试会话', lastActivity: 1000, eventCount: 1 }],
    ])
    mockUseMaisakaMonitor.mockReturnValue(makeResult({ sessions, setSelectedSession }))
    window.localStorage.setItem('maisaka-monitor-sidebar-collapsed', 'false')
    render(<MaisakaMonitorPage />)
    fireEvent.click(screen.getByText('测试会话'))
    expect(setSelectedSession).toHaveBeenCalledWith('s1')
  })

  it('connected 时显示侧边栏标题', () => {
    mockUseMaisakaMonitor.mockReturnValue(makeResult({ connected: true }))
    render(<MaisakaMonitorPage />)
    expect(screen.getByText('monitor.maisaka.chatStreams')).toBeInTheDocument()
  })
})