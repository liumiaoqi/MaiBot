/**
 * SystemStatusCard 测试（§5.4.1 测试先行）
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const stableT = (key: string) => key

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stableT }),
}))

import { SystemStatusCard } from '../system-status-card'
import type { BotStatus } from '../../types'

const formatTime = (seconds: number) => `${Math.floor(seconds / 3600)}h`

describe('SystemStatusCard', () => {
  it('running 状态展示', () => {
    const botStatus: BotStatus = { running: true, uptime: 3600, version: '2.5.4', start_time: '2026-08-12T00:00:00Z' }
    render(<SystemStatusCard botStatus={botStatus} isBotStatusLoading={false} webuiVersion="1.0.0" formatTime={formatTime} />)

    expect(screen.getByText('home.botStatus.running')).toBeInTheDocument()
    expect(screen.getByText('1h')).toBeInTheDocument()
    expect(screen.getByText('v2.5.4')).toBeInTheDocument()
    expect(screen.getByText('v1.0.0')).toBeInTheDocument()
  })

  it('stopped 状态展示', () => {
    const botStatus: BotStatus = { running: false, uptime: 0, version: '2.5.4', start_time: '2026-08-12T00:00:00Z' }
    render(<SystemStatusCard botStatus={botStatus} isBotStatusLoading={false} webuiVersion="1.0.0" formatTime={formatTime} />)

    expect(screen.getByText('home.botStatus.stopped')).toBeInTheDocument()
  })

  it('loading 状态展示', () => {
    render(<SystemStatusCard botStatus={null} isBotStatusLoading={true} webuiVersion="1.0.0" formatTime={formatTime} />)

    expect(screen.getByText('home.botStatus.loading')).toBeInTheDocument()
  })

  it('null 状态展示 unknown', () => {
    render(<SystemStatusCard botStatus={null} isBotStatusLoading={false} webuiVersion="1.0.0" formatTime={formatTime} />)

    expect(screen.getByText('home.botStatus.unknown')).toBeInTheDocument()
  })
})