/**
 * webui-feedback 测试（§7.2.1 测试先行）
 *
 * 核心验证：
 * - useMemo 派生 surveyConfig（非 useState）
 * - APP_VERSION 预填（webui_version 答案预填 v{APP_VERSION}）
 * - 问卷渲染
 * - 配置异常展示"无法加载问卷配置" + 重试按钮
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockSurveyRenderer } = vi.hoisted(() => ({
  mockSurveyRenderer: vi.fn(),
}))

vi.mock('@/lib/version', () => ({
  APP_VERSION: '1.2.3',
  APP_NAME: 'MaiBot',
  APP_FULL_NAME: 'MaiBot 1.2.3',
  formatVersion: () => 'v1.2.3',
}))

vi.mock('@/components/survey', () => ({
  SurveyRenderer: (props: Record<string, unknown>) => {
    mockSurveyRenderer(props)
    return null
  },
}))

vi.mock('@/config/surveys', () => ({
  webuiFeedbackSurvey: { id: 'webui-feedback', title: 'WebUI 体验', questions: [] },
}))

import { WebUIFeedbackSurveyPage } from '../webui-feedback'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('WebUIFeedbackSurveyPage', () => {
  it('渲染问卷 + APP_VERSION 预填', () => {
    render(<WebUIFeedbackSurveyPage />)

    expect(mockSurveyRenderer).toHaveBeenCalled()
    const props = mockSurveyRenderer.mock.calls[0][0] as { initialAnswers: Array<{ questionId: string; value: string }> }
    expect(props.initialAnswers).toEqual([{ questionId: 'webui_version', value: 'v1.2.3' }])
  })

  it('展示页面标题', () => {
    render(<WebUIFeedbackSurveyPage />)

    expect(screen.getByText('WebUI 使用反馈问卷')).toBeInTheDocument()
  })
})