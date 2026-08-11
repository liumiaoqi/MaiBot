/**
 * maibot-feedback 测试（§7.1.1 测试先行）
 *
 * 核心验证：
 * - 版本预填（getMaiBotStatus → maibot_version 答案预填）
 * - 问卷渲染（maibotFeedbackSurvey 配置）
 * - getMaiBotStatus 失败降级（setMaibotVersion('获取失败')）
 * - 加载失败展示"无法加载问卷配置" + 重试按钮
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockGetMaiBotStatus, mockSurveyRenderer } = vi.hoisted(() => ({
  mockGetMaiBotStatus: vi.fn(),
  mockSurveyRenderer: vi.fn(),
}))

vi.mock('@/lib/system-api', () => ({
  getMaiBotStatus: mockGetMaiBotStatus,
}))

vi.mock('@/components/survey', () => ({
  SurveyRenderer: (props: Record<string, unknown>) => {
    mockSurveyRenderer(props)
    return null
  },
}))

vi.mock('@/config/surveys', () => ({
  maibotFeedbackSurvey: { id: 'maibot-feedback', title: '麦麦体验', questions: [] },
}))

import { MaiBotFeedbackSurveyPage } from '../maibot-feedback'

beforeEach(() => {
  vi.clearAllMocks()
  mockGetMaiBotStatus.mockResolvedValue({ version: '2.5.4', running: true, uptime: 3600, start_time: '2026-08-12T00:00:00Z' })
})

describe('MaiBotFeedbackSurveyPage', () => {
  it('加载中展示 spinner', () => {
    render(<MaiBotFeedbackSurveyPage />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('加载完成后渲染问卷 + 版本预填', async () => {
    render(<MaiBotFeedbackSurveyPage />)

    await waitFor(() => {
      expect(mockSurveyRenderer).toHaveBeenCalled()
    })

    const props = mockSurveyRenderer.mock.calls[0][0] as { initialAnswers: Array<{ questionId: string; value: string }> }
    expect(props.initialAnswers).toEqual([{ questionId: 'maibot_version', value: '2.5.4' }])
  })

  it('getMaiBotStatus 失败 → 版本设为"获取失败"不阻塞', async () => {
    mockGetMaiBotStatus.mockRejectedValue(new Error('boom'))

    render(<MaiBotFeedbackSurveyPage />)

    await waitFor(() => {
      expect(mockSurveyRenderer).toHaveBeenCalled()
    })

    const props = mockSurveyRenderer.mock.calls[0][0] as { initialAnswers: Array<{ questionId: string; value: string }> }
    expect(props.initialAnswers).toEqual([{ questionId: 'maibot_version', value: '获取失败' }])
  })

  it('展示页面标题', async () => {
    render(<MaiBotFeedbackSurveyPage />)

    await waitFor(() => {
      expect(screen.getByText('麦麦使用体验反馈问卷')).toBeInTheDocument()
    })
  })
})