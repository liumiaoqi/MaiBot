/**
 * LLMOverviewCard 测试（§5.3.1 测试先行）
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

import { LLMOverviewCard } from '../llm-overview-card'
import type { StatisticsSummary } from '../../types'

function makeSummary(overrides: Partial<StatisticsSummary> = {}): StatisticsSummary {
  return {
    total_requests: 100,
    total_cost: 0.5,
    total_tokens: 10000,
    online_time: 3600,
    total_messages: 50,
    total_replies: 50,
    avg_response_time: 2.0,
    cost_per_hour: 0.5,
    tokens_per_hour: 10000,
    ...overrides,
  }
}

const formatNumber = (num: number) => ({ display: String(num), exact: String(num), needsExact: false })
const formatCurrency = (num: number) => ({ display: `$${num}`, exact: String(num), needsExact: false })

describe('LLMOverviewCard', () => {
  it('展示 LLM 调用概况（requests/cost/tokens）', () => {
    const summary = makeSummary()
    render(<LLMOverviewCard summary={summary} formatNumber={formatNumber} formatCurrency={formatCurrency} />)

    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText('$0.5')).toBeInTheDocument()
    expect(screen.getByText('10000')).toBeInTheDocument()
  })

  it('大数需要 exact 显示', () => {
    const summary = makeSummary({ total_requests: 1234567 })
    const fmtBig = (num: number) => ({
      display: num >= 10000 ? `${(num / 1000).toFixed(0)}k` : String(num),
      exact: String(num),
      needsExact: num >= 10000,
    })

    render(<LLMOverviewCard summary={summary} formatNumber={fmtBig} formatCurrency={formatCurrency} />)

    expect(screen.getByText('1235k')).toBeInTheDocument()
    expect(screen.getByText('(1234567)')).toBeInTheDocument()
  })
})