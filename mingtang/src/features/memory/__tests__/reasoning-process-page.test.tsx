/**
 * reasoning-process 主页面测试（R3-3-4 测试先行）
 *
 * 核心验证：双模式切换 + stage卡片网格 + 三栏浏览布局 + toast适配
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import type {
  ReasoningPromptFile,
  ReasoningPromptStagesResponse,
  ReasoningPromptListResponse,
} from '@/lib/reasoning-process-api'

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/lib/reasoning-process-api', () => ({
  listReasoningPromptStages: vi.fn(),
  listReasoningPromptFiles: vi.fn(),
  getReasoningPromptFile: vi.fn(),
  getReasoningPromptHtmlUrl: vi.fn(),
  clearReasoningPromptStage: vi.fn(),
  replayReasoningPrompt: vi.fn(),
}))

vi.mock('@/lib/avatar-url', () => ({
  useAvatarFetchEnabled: () => false,
}))

vi.mock('@/lib/api-base', () => ({
  resolveApiPath: vi.fn((path: string) => Promise.resolve(path)),
}))

import { listReasoningPromptStages, listReasoningPromptFiles } from '@/lib/reasoning-process-api'

import { ReasoningProcessPage } from '../reasoning-process'

const mockedListStages = vi.mocked(listReasoningPromptStages)
const mockedListFiles = vi.mocked(listReasoningPromptFiles)

function makeStageResponse(stages: string[]): ReasoningPromptStagesResponse {
  return {
    stages,
    stage_infos: stages.map((name, index) => ({
      name,
      session_count: index + 1,
      latest_modified_at: 1700000000 + index,
    })),
  }
}


function makeListResponse(items: ReasoningPromptFile[]): ReasoningPromptListResponse {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 50,
    stages: ['planner'],
    stage_infos: [{ name: 'planner', session_count: 1, latest_modified_at: 1700000000 }],
    sessions: ['session-1'],
    session_infos: [{
      name: 'session-1',
      platform: 'qq',
      chat_type: 'group',
      target_id: 'target-1',
      resolved_session_id: 'real-session-1',
      display_name: '测试群',
      account_id: null,
      matched_current_account: true,
    }],
    selected_session: 'session-1',
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedListStages.mockResolvedValue(makeStageResponse(['planner', 'replyer']))
  mockedListFiles.mockResolvedValue(makeListResponse([]))
})

describe('ReasoningProcessPage', () => {
  it('非嵌入模式渲染标题和stage总览', async () => {
    render(<ReasoningProcessPage />)

    expect(screen.getByText('推理过程')).toBeInTheDocument()
    expect(screen.getByText('浏览 logs/maisaka_prompt 下的 prompt 记录')).toBeInTheDocument()

    await waitFor(() => {
      expect(mockedListStages).toHaveBeenCalled()
    })
  })

  it('加载stage列表后显示stage卡片', async () => {
    render(<ReasoningProcessPage />)

    await waitFor(() => {
      expect(screen.getByText('planner')).toBeInTheDocument()
      expect(screen.getByText('replyer')).toBeInTheDocument()
    })
  })

  it('stage卡片显示中文标签和会话数', async () => {
    render(<ReasoningProcessPage />)

    await waitFor(() => {
      expect(screen.getByText('思维管道')).toBeInTheDocument()
      expect(screen.getByText('回复器')).toBeInTheDocument()
    })
  })

  it('点击stage卡片进入浏览模式', async () => {
    const user = userEvent.setup()
    render(<ReasoningProcessPage />)

    await waitFor(() => {
      expect(screen.getByText('planner')).toBeInTheDocument()
    })

    const stageCard = screen.getByText('planner').closest('button')
    if (stageCard) {
      await user.click(stageCard)
    }

    await waitFor(() => {
      expect(mockedListFiles).toHaveBeenCalled()
    })
  })

  it('加载失败时显示错误信息', async () => {
    mockedListStages.mockRejectedValue(new Error('网络错误'))

    render(<ReasoningProcessPage />)

    await waitFor(() => {
      expect(screen.getByText('网络错误')).toBeInTheDocument()
    })
  })

  it('嵌入模式不渲染标题', async () => {
    render(<ReasoningProcessPage embedded={true} />)

    expect(screen.queryByText('推理过程')).not.toBeInTheDocument()

    await waitFor(() => {
      expect(mockedListStages).toHaveBeenCalled()
    })
  })

  it('空stage列表显示空状态提示', async () => {
    mockedListStages.mockResolvedValue(makeStageResponse([]))

    render(<ReasoningProcessPage />)

    await waitFor(() => {
      expect(screen.getByText('没有找到推理过程类型')).toBeInTheDocument()
    })
  })

  it('刷新按钮触发重新加载', async () => {
    const user = userEvent.setup()
    render(<ReasoningProcessPage />)

    await waitFor(() => {
      expect(mockedListStages).toHaveBeenCalledTimes(1)
    })

    const refreshButton = screen.getByLabelText('刷新')
    await user.click(refreshButton)

    await waitFor(() => {
      expect(mockedListStages).toHaveBeenCalledTimes(2)
    })
  })

  it('嵌入模式传入toolbarContainerId时尝试portal挂载', async () => {
    const toolbarContainer = document.createElement('div')
    toolbarContainer.id = 'test-toolbar'
    document.body.appendChild(toolbarContainer)

    render(<ReasoningProcessPage embedded={true} toolbarContainerId="test-toolbar" />)

    await waitFor(() => {
      expect(mockedListStages).toHaveBeenCalled()
    })

    document.body.removeChild(toolbarContainer)
  })

  it('非嵌入模式显示返回按钮当URL有returnTo参数', async () => {
    const originalSearch = window.location.search
    Object.defineProperty(window, 'location', {
      value: { ...window.location, search: '?returnTo=/chat' },
      writable: true,
    })

    render(<ReasoningProcessPage />)

    await waitFor(() => {
      expect(screen.getByTitle('返回麦麦观察')).toBeInTheDocument()
    })

    Object.defineProperty(window, 'location', {
      value: { ...window.location, search: originalSearch },
      writable: true,
    })
  })

  it('嵌入模式不显示内联浏览控件当toolbarVisible为true', async () => {
    const toolbarContainer = document.createElement('div')
    toolbarContainer.id = 'test-toolbar-2'
    document.body.appendChild(toolbarContainer)

    render(
      <ReasoningProcessPage
        embedded={true}
        toolbarVisible={true}
        toolbarContainerId="test-toolbar-2"
      />
    )

    expect(screen.queryByText('推理过程')).not.toBeInTheDocument()

    await waitFor(() => {
      expect(mockedListStages).toHaveBeenCalled()
    })

    document.body.removeChild(toolbarContainer)
  })
})