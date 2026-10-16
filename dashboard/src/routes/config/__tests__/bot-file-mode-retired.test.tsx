import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as configApi from '@/lib/config-api'
import { BotConfigPage } from '../bot'

/**
 * `dashboard` 的「文件」（原始 TOML）入口退役后的守门用例（5 段，2026-10-16）。
 *
 * 背景：该入口原先读 `GET /config/bot/raw`、写 `POST /config/bot/raw`；那个端点会把
 * **整份 TOML 原文（含 `auth_token` / 白名单密钥真值）** 原样发给浏览器，是配置面上已知的
 * 明文密钥出站路径 ⇒ 端点已删、入口改成**说明性占位**（lmq 拍板）。
 *
 * 本文件钉两件：
 *   ① 占位**真的显示**（带原因），不是空白、也不是"点了才发现坏"的按钮；
 *   ② 进这个入口**不再发任何 raw 请求**（并把"不需要再 mock 那两个函数"这件事写死在这里）。
 *
 * ⚠️ 这是 dashboard 里**新增**的 bot 配置页测试（此前没有）。dashboard 是冻结保留，
 * 本用例只覆盖"退役"这一件事，不铺开测页面别处。
 */

const toastMock = vi.fn()

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

vi.mock('@tanstack/react-router', () => ({ Link: ({ children }: { children?: unknown }) => children }))
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('@/hooks/useUnsavedChangesGuard', () => ({ useUnsavedChangesGuard: () => undefined }))
vi.mock('@/lib/restart-context', () => ({
  RestartProvider: ({ children }: { children?: unknown }) => children,
  useRestart: () => ({ isRestarting: false, triggerRestart: vi.fn() }),
}))
vi.mock('@/components/restart-overlay', () => ({ RestartOverlay: () => null }))
// 页面 mount 时会 `fieldHooks.register(...)` 一批字段钩子 ⇒ 至少要有 register。
vi.mock('@/lib/field-hooks', () => ({
  fieldHooks: { register: vi.fn(), unregister: vi.fn(), get: vi.fn(), has: vi.fn() },
}))
// 重子组件桩掉：本用例只关心「文件」入口，不关心可视化表单渲染
vi.mock('@/components/dynamic-form', () => ({ DynamicConfigForm: () => null }))
vi.mock('@/components/dynamic-form/ConfigSectionNav', () => ({ ConfigSectionNav: () => null }))
// 部分 mock：页面 mount 时会**注册**一串 *Hook 组件（BotPlatformAccountsHook 等），
// 全量 mock 会让它们变成 undefined ⇒ 挂载即炸。只把 useAutoSave 换掉，其余保留真件。
vi.mock('../bot/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../bot/hooks')>()
  return { ...actual, useAutoSave: () => ({ triggerAutoSave: vi.fn(), cancelPendingAutoSave: vi.fn() }) }
})

// 页面从 config-api 取的全集（删掉 raw 两个之后剩这四个）；
// 注意 factory 里**故意不提供** getBotConfigRaw / updateBotConfigRaw——
// 它们已从模块删除，页面也不再 import 它们。
vi.mock('@/lib/config-api', () => ({
  getBotConfig: vi.fn(),
  getBotConfigCached: vi.fn(),
  getBotConfigSchema: vi.fn(),
  updateBotConfig: vi.fn(),
}))

const BOT_CONFIG = { bot: { nickname: '麦麦' }, chat: { max_context_size: 40 } }
const BOT_SCHEMA = { className: 'BotConfig', fields: [], nested: {} }

beforeEach(() => {
  vi.mocked(configApi.getBotConfig).mockResolvedValue(BOT_CONFIG as never)
  vi.mocked(configApi.getBotConfigCached).mockResolvedValue(BOT_CONFIG as never)
  vi.mocked(configApi.getBotConfigSchema).mockResolvedValue(BOT_SCHEMA as never)
  vi.mocked(configApi.updateBotConfig).mockResolvedValue({
    needs_restart: false,
  } as never)
})

describe('dashboard「文件」入口退役（5 段）', () => {
  it('切到「文件」显示已下线说明，且不发任何 raw 请求', async () => {
    const user = userEvent.setup()
    render(<BotConfigPage />)

    // 模式切换按钮存在（TabsTrigger value=source，文案「文件」）；
    // Radix Tabs 认的是完整指针序列 ⇒ 用 userEvent，fireEvent.click 切不过去。
    await user.click(await screen.findByText('文件'))

    // ① 说明**真的显示**，并写明原因（明文密钥出站路径 / 逃生舱关闭 / 能力未减）
    const notice = await screen.findByTestId('bot-file-mode-retired')
    expect(notice).toBeTruthy()
    expect(notice.textContent).toContain('已下线')
    expect(notice.textContent).toContain('/config/bot/raw')

    // ② 不再发 raw 请求：这两个函数已从模块删除 ⇒ 根本无从被调用。
    //    这里用"模块上不存在这两个导出"来表达"不再需要 mock"，比断言未被调用更强。
    expect('getBotConfigRaw' in configApi).toBe(false)
    expect('updateBotConfigRaw' in configApi).toBe(false)
    expect(toastMock).not.toHaveBeenCalled()
  })

  it('「文件」入口里不再渲染代码编辑器', async () => {
    const user = userEvent.setup()
    render(<BotConfigPage />)
    await user.click(await screen.findByText('文件'))

    await screen.findByTestId('bot-file-mode-retired')

    // 代码编辑器已随入口下线（dashboard 的 CodeEditor 带 data-testid='code-editor'）
    await waitFor(() => {
      expect(screen.queryByTestId('code-editor')).toBeNull()
    })
  })
})
