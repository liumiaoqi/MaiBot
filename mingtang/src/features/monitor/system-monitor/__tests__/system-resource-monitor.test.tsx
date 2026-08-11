/**
 * SystemResourceMonitor 测试（T1-6-7 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - CPU/内存/磁盘/数据库资源使用率渲染（百分比 + formatBytes）
 * - 连接状态（Wifi/WifiOff）
 * - 三态（loading / error / 数据）
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { WsEventEnvelope } from '@/lib/unified-ws'
import type { SystemResources } from '@/lib/system-api'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const { mockGetSystemResources, mockUnifiedWs } = vi.hoisted(() => {
  const listeners: Array<(msg: WsEventEnvelope) => void> = []
  const connListeners: Array<(connected: boolean) => void> = []
  return {
    mockGetSystemResources: vi.fn(),
    mockUnifiedWs: {
      getStatus: vi.fn(() => 'idle'),
      addEventListener: vi.fn((l: (msg: WsEventEnvelope) => void) => {
        listeners.push(l)
        return () => {}
      }),
      onConnectionChange: vi.fn((l: (connected: boolean) => void) => {
        connListeners.push(l)
        return () => {}
      }),
      subscribe: vi.fn(() => Promise.resolve({ ok: true })),
      unsubscribe: vi.fn(() => Promise.resolve(null)),
    },
  }
})

vi.mock('@/lib/system-api', () => ({
  getSystemResources: mockGetSystemResources,
}))

vi.mock('@/lib/unified-ws', () => ({
  unifiedWsClient: mockUnifiedWs,
}))

import { SystemResourceMonitor } from '../system-resource-monitor'

function makeResources(overrides: Partial<SystemResources> = {}): SystemResources {
  return {
    cpu_percent: 30.5,
    memory_percent: 50,
    memory_used: 4096 * 1024 * 1024,
    memory_total: 8192 * 1024 * 1024,
    disk_percent: 60,
    disk_used: 100 * 1024 * 1024 * 1024,
    disk_total: 200 * 1024 * 1024 * 1024,
    database_size: 1024 * 1024 * 1024,
    timestamp: Date.now(),
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetSystemResources.mockResolvedValue(makeResources())
})

describe('SystemResourceMonitor', () => {
  it('CPU/内存/磁盘/数据库资源渲染', async () => {
    render(<SystemResourceMonitor />)

    await waitFor(() => {
      expect(screen.getByText((c) => c.includes('30.5'))).toBeInTheDocument()
    })
    expect(screen.getByText('monitor.systemResources.cpu')).toBeInTheDocument()
    expect(screen.getByText('monitor.systemResources.memory')).toBeInTheDocument()
    expect(screen.getByText('monitor.systemResources.disk')).toBeInTheDocument()
    expect(screen.getByText('monitor.systemResources.database')).toBeInTheDocument()
    expect(screen.getAllByText((c) => c.includes('4.0 GB')).length).toBeGreaterThan(0)
    expect(screen.getAllByText((c) => c.includes('8.0 GB')).length).toBeGreaterThan(0)
    expect(screen.getByText('1.0 GB')).toBeInTheDocument()
  })

  it('连接状态：断开时显示轮询提示', async () => {
    render(<SystemResourceMonitor />)

    await waitFor(() => {
      expect(screen.getByText('monitor.systemResources.polling')).toBeInTheDocument()
    })
  })

  it('连接状态：connected 时显示实时提示', async () => {
    mockUnifiedWs.getStatus.mockReturnValue('connected')
    render(<SystemResourceMonitor />)

    await waitFor(() => {
      expect(screen.getByText('monitor.systemResources.live')).toBeInTheDocument()
    })
  })

  it('加载失败且无数据时显示错误', async () => {
    mockGetSystemResources.mockRejectedValue(new Error('boom'))
    render(<SystemResourceMonitor />)

    await waitFor(() => {
      expect(screen.getByText('monitor.systemResources.error')).toBeInTheDocument()
    })
  })

  it('无数据时显示 loading 提示', () => {
    mockGetSystemResources.mockReturnValue(new Promise(() => {}))
    render(<SystemResourceMonitor />)

    expect(screen.getByText('monitor.systemResources.loading')).toBeInTheDocument()
  })
})