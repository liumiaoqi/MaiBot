/**
 * maibot-feedback 测试（§7.1.1 测试先行）
 *
 * 核心验证：
 * - 立即渲染（P2 清理：假 loading 三态删除——静态配置无需加载，无 spinner）
 * - 版本后台预填（getMaiBotStatus → maibot_version 答案预填）
 * - getMaiBotStatus 失败降级（setMaibotVersion('获取失败')）
 * - 页面壳标题接 i18n（survey.title）
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockGetMaiBotStatus, mockSurveyRenderer } = vi.hoisted(() => ({
  mockGetMaiBotStatus: vi.fn(),
  mockSurveyRenderer: vi.fn(),
}))

// i18n mock：survey 命名空间映射到 zh.json 实际文案（保持断言可读）
const zhSurvey: Record<string, string> = {
  'survey.title': '反馈问卷',
  'survey.description': '帮助我们改进麦麦体验',
}
const t = (key: string) => zhSurvey[key] ?? key

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t }),
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
  it('立即渲染问卷（无 loading 三态）', async () => {
    render(<MaiBotFeedbackSurveyPage />)
    expect(mockSurveyRenderer).toHaveBeenCalled()
    expect(document.querySelector('.animate-spin')).not.toBeInTheDocument()

    // 吸收后台版本预填的异步 setState（避免 act 警告）
    await waitFor(() => {
      expect(mockGetMaiBotStatus).toHaveBeenCalled()
    })
  })

  it('版本后台预填：getMaiBotStatus 完成后 initialAnswers 更新', async () => {
    render(<MaiBotFeedbackSurveyPage />)

    // 后台预填是异步 re-render——轮询「最后一次」SurveyRenderer 调用（call[0] 是初始渲染的「未知版本」）
    await waitFor(() => {
      const last = mockSurveyRenderer.mock.calls.at(-1)?.[0] as { initialAnswers: Array<{ questionId: string; value: string }> }
      expect(last.initialAnswers).toEqual([{ questionId: 'maibot_version', value: '2.5.4' }])
    })
  })

  it('getMaiBotStatus 失败 → 版本设为"获取失败"不阻塞', async () => {
    mockGetMaiBotStatus.mockRejectedValue(new Error('boom'))

    render(<MaiBotFeedbackSurveyPage />)

    await waitFor(() => {
      const last = mockSurveyRenderer.mock.calls.at(-1)?.[0] as { initialAnswers: Array<{ questionId: string; value: string }> }
      expect(last.initialAnswers).toEqual([{ questionId: 'maibot_version', value: '获取失败' }])
    })
  })

  it('展示页面标题（i18n survey.title）', async () => {
    render(<MaiBotFeedbackSurveyPage />)
    expect(screen.getByText('反馈问卷')).toBeInTheDocument()
    expect(screen.getByText('帮助我们改进麦麦体验')).toBeInTheDocument()

    // 吸收后台版本预填的异步 setState（避免 act 警告）
    await waitFor(() => {
      expect(mockGetMaiBotStatus).toHaveBeenCalled()
    })
  })
})
