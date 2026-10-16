import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createElement, type ReactNode } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BotConfigPage } from '../index'
import {
  getBotConfig,
  getBotConfigSchema,
} from '@/lib/config-api'
import type { ConfigSchema, FieldSchema } from '@/types/config-schema'

/**
 * 夹具逐字取自后端 `GET /api/webui/config/schema/bot`（2026-10-16 容器内 dump）。
 * 省略了 `x-icon` / `x-layout` / `x-input-width` / `x-row` —— 本渲染器今天不消费布局元数据
 * （roadmap 已拍板"布局手设计"，见 `.shared/decisions/phase3_new_config_roadmap.md`）。
 */
const BOT_FIELDS: FieldSchema[] = [
  {
    name: 'platform',
    type: 'string',
    label: { zh_CN: '平台', en_US: 'Platform' },
    description: '麦麦主账号所在的平台，例如 qq。',
    required: false,
    default: '',
    'x-widget': 'input',
  },
  {
    name: 'qq_account',
    type: 'string',
    label: { zh_CN: 'QQ账号', en_US: 'QQ account' },
    description: '麦麦主账号 ID，用来识别哪些消息是麦麦自己发的。',
    required: false,
    default: '',
    'x-widget': 'input',
  },
  {
    name: 'platforms',
    type: 'array',
    label: { zh_CN: '其他平台' },
    description: '其他平台账号，格式为 platform:账号；没有多平台时不用填。',
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
    description: '别人可能用来称呼麦麦的名字，用于辅助识别提及。',
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

const BOT_SECTION: ConfigSchema = {
  className: 'BotConfig',
  classDoc: '机器人配置类',
  fields: BOT_FIELDS,
  nested: {},
  uiLabel: '麦麦',
}

const BOT_SCHEMA: ConfigSchema = {
  className: 'Config',
  classDoc: '麦麦配置',
  fields: [],
  nested: { bot: BOT_SECTION },
}

const BOT_CONFIG = {
  // ⚠️ 服务端昵称**故意不等于** schema 默认值（默认是"麦麦"）：若两者相等，
  // "服务端值进表单"那条断言会被 schema 默认值顺手满足 ⇒ 用例空转。
  // 变异验证：把草稿同步改坏，只有 `qq_account`（默认空串）与这里的昵称能抓住它。
  bot: { platform: 'qq', qq_account: '123456', nickname: '麦麦二号' },
  personality: { personality: '测试人格' },
}

/**
 * bot 域**今天没有任何带约束的字段**（6 个字段：3 字符串 + 3 数组，全无 `minValue`/`maxValue`）。
 * 所以"页面链路能显示越界提示"这条只能用真实约束字段作夹具——借 `chat.ascii_column_width`（32–80，
 * 逐字取自同一份 dump）。这不是伪造：字段形状与后端一致，只是不在 bot 域里。
 */
const BORROWED_CONSTRAINED_FIELD: FieldSchema = {
  name: 'ascii_column_width',
  type: 'integer',
  label: { zh_CN: 'ASCII 列宽' },
  description: 'ASCII 文本列宽（范围 32-80）。',
  required: false,
  default: 48,
  minValue: 32,
  maxValue: 80,
}

// 注：`getBotConfigRaw` / `updateBotConfigRaw` 已随 raw 端点删除，不再 mock（见同目录另一测试的说明）。
vi.mock('@/lib/config-api', () => ({
  getBotConfig: vi.fn(),
  getBotConfigSchema: vi.fn(),
  updateBotConfig: vi.fn(),
  updateBotConfigSection: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
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

/** 进详细模式并等 bot 域表单出现 */
async function openDetailMode() {
  render(<BotConfigPage />, { wrapper: createWrapper() })
  await waitFor(() => expect(screen.getByTestId('bot-mode-detail')).toBeInTheDocument())
  fireEvent.click(screen.getByTestId('bot-mode-detail'))
  await waitFor(() => expect(screen.getByTestId('bot-domain-form')).toBeInTheDocument())
}

describe('R?：bot 域字段真渲染 + 约束链端到端（task-8）', () => {
  beforeEach(() => {
    vi.mocked(getBotConfigSchema).mockResolvedValue(BOT_SCHEMA)
    vi.mocked(getBotConfig).mockResolvedValue(BOT_CONFIG)
  })

  describe('字段真渲染', () => {
    it('详细模式渲染 bot 域的 4 个非高级字段', async () => {
      await openDetailMode()
      expect(screen.getByTestId('field-platform')).toBeInTheDocument()
      expect(screen.getByTestId('field-qq_account')).toBeInTheDocument()
      expect(screen.getByTestId('field-platforms')).toBeInTheDocument()
      expect(screen.getByTestId('field-nickname')).toBeInTheDocument()
    })

    it('两个 advanced 字段默认不出（advancedVisible 默认为 false）', async () => {
      await openDetailMode()
      expect(screen.queryByTestId('field-alias_names')).not.toBeInTheDocument()
      expect(screen.queryByTestId('field-owner_user_ids')).not.toBeInTheDocument()
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
  })

  describe('编辑进 state（受控往返）', () => {
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

  describe('核心判据：约束链到用户面前', () => {
    it('页面里真填越界值 ⇒ 约束提示可见', async () => {
      vi.mocked(getBotConfigSchema).mockResolvedValue({
        ...BOT_SCHEMA,
        nested: {
          bot: {
            ...BOT_SECTION,
            fields: [...BOT_FIELDS, BORROWED_CONSTRAINED_FIELD],
          },
        },
      })
      await openDetailMode()

      expect(screen.queryByTestId('field-error-ascii_column_width')).not.toBeInTheDocument()

      fireEvent.change(inputOf('ascii_column_width'), { target: { value: '999' } })

      expect(screen.getByTestId('field-error-ascii_column_width')).toHaveTextContent('值不能大于 80')
      expect(inputOf('ascii_column_width')).toHaveAttribute('aria-invalid', 'true')
    })

    it('改回边界内的值 ⇒ 提示消失', async () => {
      vi.mocked(getBotConfigSchema).mockResolvedValue({
        ...BOT_SCHEMA,
        nested: {
          bot: {
            ...BOT_SECTION,
            fields: [...BOT_FIELDS, BORROWED_CONSTRAINED_FIELD],
          },
        },
      })
      await openDetailMode()

      fireEvent.change(inputOf('ascii_column_width'), { target: { value: '999' } })
      expect(screen.getByTestId('field-error-ascii_column_width')).toBeInTheDocument()

      fireEvent.change(inputOf('ascii_column_width'), { target: { value: '80' } })
      expect(screen.queryByTestId('field-error-ascii_column_width')).not.toBeInTheDocument()
    })

    it('bot 域真实数据（无约束字段）⇒ 一条提示都不出现（防误报）', async () => {
      await openDetailMode()
      expect(document.body.querySelectorAll('[data-testid^="field-error-"]')).toHaveLength(0)
    })
  })
})
