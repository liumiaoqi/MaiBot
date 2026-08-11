/**
 * ChatStreamCard 测试（§5.2.1 测试先行）
 */
import { render, screen } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, className }: { to: string; children: ReactNode; className?: string }) =>
    createElement('a', { href: to, className, 'data-testid': 'link' }, children),
}))

const stableT = (key: string) => key

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stableT }),
}))

import { ChatStreamCard } from '../chat-stream-card'
import type { AgentStatsInfo, RecentActivity } from '../../types'

describe('ChatStreamCard', () => {
  it('展示聊天流活跃度（active sessions + today calls）', () => {
    const agentStats: AgentStatsInfo = { total_agents: 2, active_agents: 1, total_active_sessions: 3 }
    const now = new Date()
    const recentActivity: RecentActivity[] = [
      { timestamp: now.toISOString(), model: 'gpt-4', request_type: 'chat', tokens: 100, cost: 0.01, time_cost: 1.0, status: 'ok' },
      { timestamp: now.toISOString(), model: 'gpt-4', request_type: 'chat', tokens: 200, cost: 0.02, time_cost: 2.0, status: 'ok' },
    ]

    render(<ChatStreamCard agentStats={agentStats} recentActivity={recentActivity} />)

    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('无今日活动 → today calls=0', () => {
    const agentStats: AgentStatsInfo = { total_agents: 2, active_agents: 1, total_active_sessions: 0 }
    const recentActivity: RecentActivity[] = [
      { timestamp: '2020-01-01T00:00:00Z', model: 'gpt-4', request_type: 'chat', tokens: 100, cost: 0.01, time_cost: 1.0, status: 'ok' },
    ]

    render(<ChatStreamCard agentStats={agentStats} recentActivity={recentActivity} />)

    // active sessions=0 + today calls=0 → 两个 '0'
    const zeros = screen.getAllByText('0')
    expect(zeros).toHaveLength(2)
  })
})