/**
 * AgentStatusCard 测试（§5.1.1 测试先行）
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

import { AgentStatusCard } from '../agent-status-card'
import type { AgentStatsInfo } from '../../types'

describe('AgentStatusCard', () => {
  it('展示智能体状态（active/total/sessions）', () => {
    const agentStats: AgentStatsInfo = { total_agents: 3, active_agents: 2, total_active_sessions: 5 }
    render(<AgentStatusCard agentStats={agentStats} />)

    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('agentStats 为 undefined → 展示 --', () => {
    render(<AgentStatusCard agentStats={undefined} />)

    const dashes = screen.getAllByText('--')
    expect(dashes).toHaveLength(3)
  })
})