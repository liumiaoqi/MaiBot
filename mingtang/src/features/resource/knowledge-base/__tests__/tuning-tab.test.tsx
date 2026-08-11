/**
 * TuningTab 组件测试（R4-2-11）
 *
 * 核心验证：
 * - 渲染基本结构（调优任务卡片 + 快照卡片）
 * - 核心交互（点击"创建任务" → submitTuningTask）
 * - 加载态（creatingTuning: true → 按钮禁用）
 * - 空态（tuningTasks 为空 → 空态文案）
 * - 任务列表渲染（tuningTasks 非空 → 任务卡片显示）
 *
 * 模式：props 注入 mock hook 结果 + mock react-i18next（R4-1 教训 #6/#7）
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (options && typeof options === 'object') {
        let result = key
        for (const [k, v] of Object.entries(options)) {
          result = result.replace(`{{${k}}}`, String(v))
        }
        return result
      }
      return key
    },
  }),
}))

import { Tabs } from '@/components/ui/tabs'

import type { UseMemoryTuningResult } from '../hooks/useMemoryTuning'
import { TuningTab } from '../tabs/TuningTab'

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  Wrapper.displayName = 'QueryWrapper'
  return Wrapper
}

function renderTuningTab(tuning: UseMemoryTuningResult) {
  return render(
    <Tabs value="tuning">
      <TuningTab tuning={tuning} />
    </Tabs>,
    { wrapper: makeWrapper() },
  )
}

function makeMockTuning(overrides: Partial<UseMemoryTuningResult> = {}): UseMemoryTuningResult {
  return {
    tuningObjective: 'precision_priority',
    setTuningObjective: vi.fn(),
    tuningIntensity: 'standard',
    setTuningIntensity: vi.fn(),
    tuningSampleSize: '24',
    setTuningSampleSize: vi.fn(),
    tuningTopKEval: '20',
    setTuningTopKEval: vi.fn(),
    persistBestProfile: false,
    setPersistBestProfile: vi.fn(),
    submitTuningTask: vi.fn(),
    creatingTuning: false,
    tuningProfile: { runtime: {}, persistable: {} },
    tuningProfileToml: '',
    tuningTasks: [],
    applyBestTask: vi.fn(),
    tuningErrorText: '',
    ...overrides,
  }
}

describe('R4-2-11 TuningTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染基本结构：调优任务表单 + 快照卡片', () => {
    renderTuningTab(makeMockTuning())
    // t() 返回 key，验证关键 key 出现
    expect(screen.getByText('memory.tuning.task.title')).toBeInTheDocument()
    expect(screen.getByText('memory.tuning.snapshot.title')).toBeInTheDocument()
    expect(screen.getByText('memory.tuning.tasks.title')).toBeInTheDocument()
  })

  it('核心交互：点击"创建任务" → submitTuningTask 调用', () => {
    const tuning = makeMockTuning()
    renderTuningTab(tuning)
    const button = screen.getByRole('button', { name: 'memory.tuning.actions.createTask' })
    fireEvent.click(button)
    expect(tuning.submitTuningTask).toHaveBeenCalledTimes(1)
  })

  it('加载态：creatingTuning: true → 创建按钮禁用', () => {
    const tuning = makeMockTuning({ creatingTuning: true })
    renderTuningTab(tuning)
    const button = screen.getByRole('button', { name: 'memory.tuning.actions.createTask' })
    expect(button).toBeDisabled()
  })

  it('空态：tuningTasks 为空 → 空态文案呈现', () => {
    renderTuningTab(makeMockTuning())
    expect(screen.getByText('memory.tuning.tasks.empty')).toBeInTheDocument()
  })

  it('任务列表渲染：tuningTasks 非空 → 任务卡片显示', () => {
    const tuning = makeMockTuning({
      tuningTasks: [
        {
          task_id: 'tuning-1',
          status: 'completed',
          created_at: 1700000000,
          updated_at: 1700000000,
          validation_summary: { recommended: true },
        },
      ],
    })
    renderTuningTab(tuning)
    expect(screen.getByText('tuning-1')).toBeInTheDocument()
  })
})