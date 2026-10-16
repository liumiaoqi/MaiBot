import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createElement, type ReactNode } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BotConfigPage } from '../index'
import { getBotConfig, getBotConfigRaw, getBotConfigSchema } from '@/lib/config-api'
import type { ConfigSchema, FieldSchema } from '@/types/config-schema'

/**
 * 夹具逐字取自后端 `GET /api/webui/config/schema/bot` 的 `bot` 域（2026-10-16 容器内 dump）。
 * 省略 `x-icon` / `x-layout` / `x-input-width` / `x-row`（本渲染器不消费布局元数据）。
 *
 * ⚠️ 本域 6 个字段里 **3 个是 array + `x-widget: custom`**（`platforms` / `alias_names` /
 * `owner_user_ids`）⇒ 按 (a)-⑤ 的红线**显式不渲染**（`fieldHooks` 是空壳，数组会落到文本框兜底、
 * 编辑后 state 里是字符串 ⇒ 接落盘会写坏类型）。所以本域只有 3 个标量字段会渲染。
 */
const BOT_FIELDS: FieldSchema[] = [
  {
    name: 'platform',
    type: 'string',
    label: { zh_CN: '平台' },
    description: '麦麦主账号所在的平台，例如 qq。',
    required: false,
    default: '',
    'x-widget': 'input',
  },
  {
    name: 'qq_account',
    type: 'string',
    label: { zh_CN: 'QQ账号' },
    description: '麦麦主账号 ID，用来识别哪些消息是麦麦自己发的。',
    required: false,
    default: '',
    'x-widget': 'input',
  },
  {
    name: 'platforms',
    type: 'array',
    label: { zh_CN: '其他平台' },
    description: '其他平台账号，格式为 platform:账号。',
    required: false,
    items: { type: 'string' },
    'x-widget': 'custom',
  },
  {
    name: 'nickname',
    type: 'string',
    label: { zh_CN: '机器人昵称' },
    description: '麦麦显示和自称时使用的名字。',
    required: false,
    default: '麦麦',
    'x-widget': 'input',
  },
  {
    name: 'alias_names',
    type: 'array',
    label: { zh_CN: '别名' },
    description: '别人可能用来称呼麦麦的名字。',
    required: false,
    items: { type: 'string' },
    'x-widget': 'custom',
    advanced: true,
  },
  {
    name: 'owner_user_ids',
    type: 'array',
    label: { zh_CN: '主人用户ID' },
    description: 'bot主人的用户ID列表。',
    required: false,
    items: { type: 'string' },
    'x-widget': 'custom',
    advanced: true,
  },
]

const SCHEMA: ConfigSchema = {
  className: 'Config',
  classDoc: '麦麦配置',
  fields: [],
  nested: {
    bot: {
      className: 'BotConfig',
      classDoc: '机器人配置类',
      fields: BOT_FIELDS,
      nested: {},
      uiLabel: '基础',
      uiOrder: 10,
    },
  },
}

const CONFIG = {
  // ⚠️ 服务端昵称**故意不等于** schema 默认值（默认是"麦麦"）：相等的话
  // "服务端值进表单"那条断言会被 schema 默认值顺手满足 ⇒ 用例空转。
  bot: { platform: 'qq', qq_account: '123456', nickname: '麦麦二号' },
}

vi.mock('@/lib/config-api', () => ({
  getBotConfig: vi.fn(),
  getBotConfigSchema: vi.fn(),
  getBotConfigRaw: vi.fn(),
  updateBotConfig: vi.fn(),
  updateBotConfigSection: vi.fn(),
  updateBotConfigRaw: vi.fn(),
}))

// `i18n` 必须给：真实 useTranslation() 一定返回它，页面要用 i18n.language 解析 LocalizedText
// （只 mock `t` 会让页面在渲染期崩——那是 mock 不完整，不是页面写错了）
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'zh-CN' } }),
}))

vi.mock('../../hooks', () => ({
  registerAllConfigHooks: vi.fn(),
}))

/** 取字段的输入控件——`data-testid=field-<name>` 内唯一的 input */
function inputOf(name: string): HTMLInputElement {
  const control = screen.getByTestId(`field-${name}`).querySelector('input')
  if (!(control instanceof HTMLInputElement)) {
    throw new Error(`字段 ${name} 未渲染 input 控件`)
  }
  return control
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

async function openDetailMode() {
  render(<BotConfigPage />, { wrapper: createWrapper() })
  await waitFor(() => expect(screen.getByTestId('bot-mode-detail')).toBeInTheDocument())
  fireEvent.click(screen.getByTestId('bot-mode-detail'))
  await waitFor(() => expect(screen.getByTestId('wired-domain-form')).toBeInTheDocument())
}

beforeEach(() => {
  vi.mocked(getBotConfig).mockResolvedValue(CONFIG)
  vi.mocked(getBotConfigSchema).mockResolvedValue(SCHEMA)
  vi.mocked(getBotConfigRaw).mockResolvedValue('')
})

describe('(a)-⑤ · bot 域（页面默认域）的字段渲染', () => {
  it('渲染 3 个标量字段', async () => {
    await openDetailMode()
    expect(screen.getByTestId('field-platform')).toBeInTheDocument()
    expect(screen.getByTestId('field-qq_account')).toBeInTheDocument()
    expect(screen.getByTestId('field-nickname')).toBeInTheDocument()
  })

  it('3 个 array 字段显式不渲染，并在提示里列出名字', async () => {
    await openDetailMode()

    expect(screen.queryByTestId('field-platforms')).not.toBeInTheDocument()
    expect(screen.queryByTestId('field-alias_names')).not.toBeInTheDocument()
    expect(screen.queryByTestId('field-owner_user_ids')).not.toBeInTheDocument()

    const notice = screen.getByTestId('domain-skipped-fields')
    expect(notice).toHaveTextContent('未渲染 3 个字段')
    expect(notice).toHaveTextContent('platforms')
    expect(notice).toHaveTextContent('alias_names')
    expect(notice).toHaveTextContent('owner_user_ids')
  })

  it('服务端值进表单（两个字段都区别于各自 schema 默认值）', async () => {
    await openDetailMode()
    expect(inputOf('nickname')).toHaveValue('麦麦二号')
    expect(inputOf('qq_account')).toHaveValue('123456')
  })

  it('字段可编辑（页面确实传了 onChange ⇒ 没有 disabled）', async () => {
    await openDetailMode()
    expect(inputOf('nickname')).not.toBeDisabled()
  })

  it('无约束字段不产生提示（防误报）', async () => {
    await openDetailMode()
    expect(document.body.querySelectorAll('[data-testid^="field-error-"]')).toHaveLength(0)
  })
})

describe('(a)-⑤ · bot 域编辑进 state（受控往返）', () => {
  it('改昵称 → 输入框回显新值（值经 state 回到 props）', async () => {
    await openDetailMode()
    const control = inputOf('nickname')

    fireEvent.change(control, { target: { value: '白露' } })

    expect(inputOf('nickname')).toHaveValue('白露')
    expect(inputOf('nickname')).not.toHaveValue('麦麦二号')
  })

  it('多次编辑互不覆盖（后一次编辑保留前一次）', async () => {
    await openDetailMode()

    fireEvent.change(inputOf('nickname'), { target: { value: '白露' } })
    fireEvent.change(inputOf('qq_account'), { target: { value: '654321' } })

    expect(inputOf('nickname')).toHaveValue('白露')
    expect(inputOf('qq_account')).toHaveValue('654321')
  })
})
