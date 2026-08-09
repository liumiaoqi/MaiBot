/**
 * reasoning-replay-panel 重放子系统测试（R3-3-2 测试先行）
 *
 * 核心验证：模型/温度/次数输入 + 批量重放不阻塞 UI + ReplayResultItem 结果展示
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import type { ReasoningPromptFile, ReasoningReplayResponse } from '@/lib/reasoning-process-api'

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/lib/reasoning-process-api', () => ({
  replayReasoningPrompt: vi.fn(),
}))

import { toast } from 'sonner'
import { replayReasoningPrompt } from '@/lib/reasoning-process-api'

import { ReasoningReplayPanel } from '../components/replay/reasoning-replay-panel'
import { ReplayResultItem } from '../components/replay/replay-result-item'
import { ReplayMessageEditorColumn } from '../components/replay/replay-message-editor-column'
import type { EditableReplayMessage, ReplayRunResult } from '../utils/replay-prepare'

const mockedReplay = vi.mocked(replayReasoningPrompt)
const mockedToastError = vi.mocked(toast.error)
const mockedToastSuccess = vi.mocked(toast.success)

function makeFile(overrides: Partial<ReasoningPromptFile> = {}): ReasoningPromptFile {
  return {
    stage: 'planner',
    session_id: 'session-1',
    resolved_session_id: null,
    session_display_name: null,
    platform: 'qq',
    chat_type: 'group',
    target_id: 'target-1',
    stem: 'stem-1',
    timestamp: null,
    text_path: null,
    html_path: null,
    json_path: '/path/to/file.json',
    output_preview: null,
    action_preview: null,
    display_title: null,
    related_json_paths: [],
    model_name: 'test-model',
    duration_ms: null,
    size: 100,
    modified_at: 1700000000,
    ...overrides,
  }
}

function makeReplayResponse(overrides: Partial<ReasoningReplayResponse> = {}): ReasoningReplayResponse {
  return {
    response: '测试回复',
    reasoning: '',
    model_name: 'test-model',
    tool_calls: null,
    prompt_tokens: 100,
    completion_tokens: 50,
    total_tokens: 150,
    prompt_cache_hit_tokens: 0,
    prompt_cache_miss_tokens: 0,
    duration_ms: 500,
    error: null,
    ...overrides,
  }
}

function makeEditableMessage(overrides: Partial<EditableReplayMessage> = {}): EditableReplayMessage {
  return {
    id: 'msg-1',
    role: 'user',
    contentText: '你好',
    originalContent: '你好',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedReplay.mockResolvedValue(makeReplayResponse())
})

describe('ReasoningReplayPanel', () => {
  it('面板打开时渲染重放表单', () => {
    render(
      <ReasoningReplayPanel
        open={true}
        onClose={vi.fn()}
        selected={makeFile()}
        selectedTitle="测试标题"
        structuredPrompt={null}
        messages={[makeEditableMessage()]}
      />
    )
    expect(screen.getByText('重放推理请求')).toBeInTheDocument()
    expect(screen.getByText('测试标题')).toBeInTheDocument()
    expect(screen.getByLabelText('模型名称')).toBeInTheDocument()
    expect(screen.getByLabelText('温度')).toBeInTheDocument()
    expect(screen.getByLabelText('最大 Token')).toBeInTheDocument()
    expect(screen.getByLabelText('次数')).toBeInTheDocument()
  })

  it('面板关闭时隐藏', () => {
    render(
      <ReasoningReplayPanel
        open={false}
        onClose={vi.fn()}
        selected={null}
        selectedTitle=""
        structuredPrompt={null}
        messages={[]}
      />
    )
    const aside = screen.getByText('重放推理请求').closest('aside')
    expect(aside).toHaveClass('hidden')
  })

  it('空消息时执行按钮禁用', () => {
    render(
      <ReasoningReplayPanel
        open={true}
        onClose={vi.fn()}
        selected={makeFile()}
        selectedTitle="测试"
        structuredPrompt={null}
        messages={[]}
      />
    )
    const button = screen.getByText('执行重放')
    expect(button).toBeDisabled()
  })

  it('缺少模型名称时 toast 报错', async () => {
    const user = userEvent.setup()
    render(
      <ReasoningReplayPanel
        open={true}
        onClose={vi.fn()}
        selected={makeFile({ model_name: null })}
        selectedTitle="测试"
        structuredPrompt={null}
        messages={[makeEditableMessage()]}
      />
    )
    const modelInput = screen.getByLabelText('模型名称')
    await user.clear(modelInput)
    const button = screen.getByText('执行重放')
    await user.click(button)
    expect(mockedToastError).toHaveBeenCalledWith('缺少模型名称', expect.any(Object))
  })

  it('handleReplay 批量执行调用 replayReasoningPrompt', async () => {
    const user = userEvent.setup()
    render(
      <ReasoningReplayPanel
        open={true}
        onClose={vi.fn()}
        selected={makeFile()}
        selectedTitle="测试"
        structuredPrompt={null}
        messages={[makeEditableMessage()]}
      />
    )
    const modelInput = screen.getByLabelText('模型名称')
    await user.clear(modelInput)
    await user.type(modelInput, 'test-model')
    const button = screen.getByText('执行重放')
    await user.click(button)
    await waitFor(() => {
      expect(mockedReplay).toHaveBeenCalled()
    })
    expect(mockedToastSuccess).toHaveBeenCalledWith('批量重放完成', expect.any(Object))
  })
})

describe('ReplayResultItem', () => {
  it('失败状态展示错误信息', () => {
    const item: ReplayRunResult = {
      id: 'r1',
      index: 1,
      result: null,
      error: '网络错误',
    }
    render(<ReplayResultItem item={item} />)
    expect(screen.getByText('#1 失败')).toBeInTheDocument()
    expect(screen.getByText('网络错误')).toBeInTheDocument()
  })

  it('成功状态展示模型回复', () => {
    const item: ReplayRunResult = {
      id: 'r1',
      index: 1,
      result: makeReplayResponse({ response: '回复内容' }),
      error: null,
    }
    render(<ReplayResultItem item={item} />)
    expect(screen.getByText('#1 完成')).toBeInTheDocument()
    expect(screen.getByText('回复内容')).toBeInTheDocument()
  })

  it('空回复展示提示文本', () => {
    const item: ReplayRunResult = {
      id: 'r1',
      index: 1,
      result: makeReplayResponse({ response: '' }),
      error: null,
    }
    render(<ReplayResultItem item={item} />)
    expect(screen.getByText('模型未返回正文。')).toBeInTheDocument()
  })

  it('有推理内容展示推理折叠区', () => {
    const item: ReplayRunResult = {
      id: 'r1',
      index: 1,
      result: makeReplayResponse({ response: '', reasoning: '推理过程' }),
      error: null,
    }
    render(<ReplayResultItem item={item} />)
    expect(screen.getByText('推理内容')).toBeInTheDocument()
    expect(screen.getByText('推理过程')).toBeInTheDocument()
  })
})

describe('ReplayMessageEditorColumn', () => {
  it('渲染消息列表', () => {
    const messages = [
      makeEditableMessage({ id: 'm1', role: 'user', contentText: '你好' }),
      makeEditableMessage({ id: 'm2', role: 'assistant', contentText: '回复' }),
    ]
    render(
      <ReplayMessageEditorColumn
        selectedTitle="测试"
        messages={messages}
        updateMessage={vi.fn()}
        addMessage={vi.fn()}
        deleteMessage={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByText('编辑重放消息')).toBeInTheDocument()
    expect(screen.getByText('2 条')).toBeInTheDocument()
    expect(screen.getByText('你好')).toBeInTheDocument()
    expect(screen.getByText('回复')).toBeInTheDocument()
  })

  it('空消息列表展示占位文本', () => {
    render(
      <ReplayMessageEditorColumn
        selectedTitle="测试"
        messages={[]}
        updateMessage={vi.fn()}
        addMessage={vi.fn()}
        deleteMessage={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByText('这条记录没有可重放的结构化 messages。')).toBeInTheDocument()
  })

  it('添加消息按钮触发 addMessage', async () => {
    const user = userEvent.setup()
    const addMessage = vi.fn()
    render(
      <ReplayMessageEditorColumn
        selectedTitle="测试"
        messages={[makeEditableMessage()]}
        updateMessage={vi.fn()}
        addMessage={addMessage}
        deleteMessage={vi.fn()}
        onClose={vi.fn()}
      />
    )
    await user.click(screen.getByText('添加消息'))
    expect(addMessage).toHaveBeenCalledOnce()
  })
})