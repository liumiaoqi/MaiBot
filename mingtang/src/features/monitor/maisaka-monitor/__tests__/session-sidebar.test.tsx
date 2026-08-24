/**
 * SessionSidebar 子组件测试
 *
 * 核心验证：
 * - 会话倒序排列（按 lastActivity 降序）
 * - 空状态占位
 * - 折叠态（仅头像列）
 * - 选中态高亮
 */
import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
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

import { SessionSidebar } from '../components/session-sidebar'
import type { SessionInfo } from '../hooks/persist-monitor'

function makeSession(id: string, name: string, lastActivity: number): SessionInfo {
  return {
    sessionId: id,
    sessionName: name,
    lastActivity,
    eventCount: 1,
  }
}

function makeSessions(...sessions: SessionInfo[]): Map<string, SessionInfo> {
  return new Map(sessions.map((s) => [s.sessionId, s]))
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SessionSidebar', () => {
  it('会话按 lastActivity 倒序排列', () => {
    const sessions = makeSessions(
      makeSession('s1', '旧会话', 1000),
      makeSession('s2', '新会话', 2000),
      makeSession('s3', '最新会话', 3000),
    )
    render(
      <SessionSidebar
        sessions={sessions}
        stageStatuses={new Map()}
        selectedSession={null}
        onSelect={vi.fn()}
        collapsed={false}
      />,
    )

    const buttons = screen.getAllByRole('button')
    expect(buttons[0]).toHaveAttribute('title', '最新会话')
    expect(buttons[1]).toHaveAttribute('title', '新会话')
    expect(buttons[2]).toHaveAttribute('title', '旧会话')
  })

  it('空状态显示占位文案', () => {
    render(
      <SessionSidebar
        sessions={new Map()}
        stageStatuses={new Map()}
        selectedSession={null}
        onSelect={vi.fn()}
        collapsed={false}
      />,
    )
    expect(screen.getByText('monitor.maisaka.waitingSession')).toBeInTheDocument()
  })

  it('折叠态不显示会话名', () => {
    const sessions = makeSessions(makeSession('s1', '测试会话', 1000))
    render(
      <SessionSidebar
        sessions={sessions}
        stageStatuses={new Map()}
        selectedSession={null}
        onSelect={vi.fn()}
        collapsed={true}
      />,
    )
    expect(screen.queryByText('测试会话')).not.toBeInTheDocument()
  })

  it('展开态显示会话名和事件计数', () => {
    const sessions = makeSessions(makeSession('s1', '测试会话', 1000))
    render(
      <SessionSidebar
        sessions={sessions}
        stageStatuses={new Map()}
        selectedSession={null}
        onSelect={vi.fn()}
        collapsed={false}
      />,
    )
    expect(screen.getByText('测试会话')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('选中态高亮（bg-accent class）', () => {
    const sessions = makeSessions(makeSession('s1', '测试会话', 1000))
    render(
      <SessionSidebar
        sessions={sessions}
        stageStatuses={new Map()}
        selectedSession="s1"
        onSelect={vi.fn()}
        collapsed={false}
      />,
    )
    const btn = screen.getByRole('button')
    expect(btn.className).toContain('bg-accent')
  })

  it('点击会话调用 onSelect', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    const sessions = makeSessions(makeSession('s1', '测试会话', 1000))
    render(
      <SessionSidebar
        sessions={sessions}
        stageStatuses={new Map()}
        selectedSession={null}
        onSelect={onSelect}
        collapsed={false}
      />,
    )
    await user.click(screen.getByText('测试会话'))
    expect(onSelect).toHaveBeenCalledWith('s1')
  })
})