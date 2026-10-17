/**
 * 关系真值回路页测试（测试先行）
 *
 * 核心验证：
 * - `decision` 必须显式三选（未选 ⇒ 一个请求都不发，不静默当 neutral）
 * - 请求体恰好 4 键（target / decision / reason / updated_by；不发 `strength`）
 *   —— 后端 `V5ActionRequest` 是 `extra='forbid'`：多一个键就是 422
 * - 成功 / 失败都有可见反馈
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { backendApi } from '@/lib/http'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import { toast } from 'sonner'

import { MemoryRelationsPage } from '../index'

import en from '@/i18n/locales/en.json'
import ja from '@/i18n/locales/ja.json'
import ko from '@/i18n/locales/ko.json'
import zh from '@/i18n/locales/zh.json'

const FEEDBACK_PATH = '/api/webui/memory/relations/feedback'

/** 直接读真 JSON——i18n 在页面用例里被 mock 成 key 透传，键路径写错不会红 */
function decisionsOf(locale: unknown): Record<string, string> | undefined {
  const root = locale as {
    memoryRelations?: { form?: { decisions?: Record<string, string> } }
  }
  return root.memoryRelations?.form?.decisions
}

describe('MemoryRelationsPage（关系真值回路）', () => {
  let postSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.clearAllMocks()
    postSpy = vi.spyOn(backendApi, 'post').mockResolvedValue({
      success: true,
      relation_hash: 'rel-1',
      action: 'raise',
      delta: 0.1,
      confidence_after: 0.9,
      event_id: 7,
    })
  })

  afterEach(() => {
    postSpy.mockRestore()
  })

  it('未选择判断时拒绝提交（decision 显式三选）', async () => {
    const user = userEvent.setup()
    render(<MemoryRelationsPage />)

    await user.type(screen.getByLabelText('memoryRelations.form.target'), 'rel-1')
    await user.click(screen.getByRole('button', { name: 'memoryRelations.form.submit' }))

    expect(postSpy).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledWith('memoryRelations.errors.decisionRequired')
  })

  it('提交只发 4 键（target/decision/reason/updated_by），不发 strength', async () => {
    const user = userEvent.setup()
    render(<MemoryRelationsPage />)

    await user.type(screen.getByLabelText('memoryRelations.form.target'), 'rel-1')
    await user.click(
      screen.getByRole('radio', { name: 'memoryRelations.form.decisions.raise' })
    )
    await user.type(screen.getByLabelText('memoryRelations.form.reason'), '她最近主动找我')

    const updatedBy = screen.getByLabelText('memoryRelations.form.updatedBy')
    await user.clear(updatedBy)
    await user.type(updatedBy, 'lmq')

    await user.click(screen.getByRole('button', { name: 'memoryRelations.form.submit' }))

    await waitFor(() => expect(postSpy).toHaveBeenCalledTimes(1))
    const call = postSpy.mock.calls[0] as unknown as [string, { body: Record<string, unknown> }]
    expect(call[0]).toBe(FEEDBACK_PATH)
    expect(call[1].body).toEqual({
      target: 'rel-1',
      decision: 'raise',
      reason: '她最近主动找我',
      updated_by: 'lmq',
    })
    expect(Object.keys(call[1].body)).toHaveLength(4)
    expect(toast.success).toHaveBeenCalledWith('memoryRelations.result.success')
  })

  it('后端拒绝时把具名错误展示出来', async () => {
    postSpy.mockResolvedValue({ success: false, error: 'relation_hash 为空' })
    const user = userEvent.setup()
    render(<MemoryRelationsPage />)

    await user.type(screen.getByLabelText('memoryRelations.form.target'), 'rel-missing')
    await user.click(
      screen.getByRole('radio', { name: 'memoryRelations.form.decisions.neutral' })
    )
    await user.click(screen.getByRole('button', { name: 'memoryRelations.form.submit' }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('relation_hash 为空')
    )
  })

  it('四种语言的 decision 三选文案齐全（i18n 成对搬）', () => {
    const locales: Array<[string, unknown]> = [
      ['zh', zh],
      ['en', en],
      ['ja', ja],
      ['ko', ko],
    ]
    locales.forEach(([name, locale]) => {
      const decisions = decisionsOf(locale)
      expect(decisions, name).toBeTruthy()
      expect(Object.keys(decisions ?? {}).sort(), name).toEqual(['lower', 'neutral', 'raise'])
    })
  })
})
