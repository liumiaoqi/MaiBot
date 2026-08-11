/**
 * DeepMonitorLink 测试（T2-10-1 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 跨域跳转 3 目标路由（/emotion-monitor /relationship-monitor /subagent-monitor）
 * - search 携带 agent 参数（TanStack Router Link 的 to + search props）
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const mockLink = vi.hoisted(() => vi.fn())

vi.mock('@tanstack/react-router', () => ({
  Link: (props: { to: string; search: { agent: string }; children: React.ReactNode; className?: string }) => {
    mockLink(props)
    return <a data-to={props.to} data-search={JSON.stringify(props.search)} className={props.className}>{props.children}</a>
  },
}))

import { DeepMonitorLink } from '../components/inner-world/deep-monitor-link'

describe('DeepMonitorLink', () => {
  it('target=emotion → /emotion-monitor + search.agent', () => {
    render(<DeepMonitorLink agentId="agent-a" target="emotion" />)

    const link = screen.getByText('agent.emotionLandscape.deepMonitor').closest('a')
    expect(link).toHaveAttribute('data-to', '/emotion-monitor')
    expect(JSON.parse(link!.getAttribute('data-search')!)).toEqual({ agent: 'agent-a' })
  })

  it('target=relationship → /relationship-monitor', () => {
    render(<DeepMonitorLink agentId="agent-b" target="relationship" />)

    const link = screen.getByText('agent.emotionLandscape.deepMonitor').closest('a')
    expect(link).toHaveAttribute('data-to', '/relationship-monitor')
    expect(JSON.parse(link!.getAttribute('data-search')!)).toEqual({ agent: 'agent-b' })
  })

  it('target=subagent → /subagent-monitor', () => {
    render(<DeepMonitorLink agentId="agent-c" target="subagent" />)

    const link = screen.getByText('agent.emotionLandscape.deepMonitor').closest('a')
    expect(link).toHaveAttribute('data-to', '/subagent-monitor')
    expect(JSON.parse(link!.getAttribute('data-search')!)).toEqual({ agent: 'agent-c' })
  })

  it('Link props 完整传递（to + search）', () => {
    render(<DeepMonitorLink agentId="agent-a" target="subagent" />)

    expect(mockLink).toHaveBeenCalledWith(
      expect.objectContaining({
        to: '/subagent-monitor',
        search: { agent: 'agent-a' },
      })
    )
  })
})