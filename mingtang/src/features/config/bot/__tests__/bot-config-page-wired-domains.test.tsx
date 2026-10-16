import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createElement, type ReactNode } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BotConfigPage } from '../index'
import type { ConfigSchema, FieldSchema } from '@/types/config-schema'

/**
 * 夹具**逐字取自后端** `ConfigSchemaGenerator`（2026-10-16 容器内 dump）。
 * 只保留本文件要断言的字段（省略 `x-icon` / `x-layout` / `x-row` 等本渲染器不消费的布局元数据）。
 *
 * 为什么用真字段而不是编一个：**约束值本身就是要验的东西**（2..20 / 32..80 / 0..100），
 * 编出来的夹具只能证明"我写的代码和我写的测试一致"。
 */
const AGENT_AUTONOMY_FIELDS: FieldSchema[] = [
  {
    name: 'enabled',
    type: 'boolean',
    label: { zh_CN: '启用智能体自主性' },
    description: '启用后，智能体将以角色内部视角思考。',
    required: false,
    default: true,
    'x-widget': 'switch',
  },
  {
    name: 'max_active_agents',
    type: 'integer',
    label: { zh_CN: '最大活跃智能体数' },
    description: '同一会话中同时活跃的智能体数量上限。',
    required: false,
    default: 13,
    'x-widget': 'input',
    minValue: 2,
    maxValue: 20,
  },
  {
    name: 'interjection_intent_threshold',
    type: 'number',
    label: { zh_CN: '插话意图阈值' },
    description: '行为意图强度达到此阈值才可能触发插话。',
    required: false,
    default: 60,
    'x-widget': 'input',
    minValue: 0,
    maxValue: 100,
  },
  {
    name: 'speaker_tag_format',
    type: 'string',
    label: { zh_CN: '发言者标签格式' },
    description: '高级字段：留空用默认格式。',
    required: false,
    advanced: true,
    'x-widget': 'input',
  },
]

const CHAT_FIELDS: FieldSchema[] = [
  {
    name: 'mid_term_memory_lenth',
    type: 'integer',
    label: { zh_CN: '聊天回想保留数' },
    description: '最多保留多少条聊天回想；设为 0 表示不保留。',
    required: false,
    default: 10,
    'x-widget': 'input',
    minValue: 0,
  },
  {
    name: 'ascii_column_width',
    type: 'integer',
    label: { zh_CN: 'ASCII 列宽' },
    description: 'ASCII 文本列宽（范围 32-80）。',
    required: false,
    default: 48,
    'x-widget': 'input',
    minValue: 32,
    maxValue: 80,
  },
  // 真形状：chat 的 fields 里确实带两个 object（它们同时又是 nested 子域）
  {
    name: 'reply_timing',
    type: 'object',
    label: { zh_CN: 'reply_timing' },
    description: '什么时候回复、回复频率与等待退避配置。',
    required: false,
  },
  {
    name: 'reply_style',
    type: 'object',
    label: { zh_CN: 'reply_style' },
    description: '如何回复、引用回复与聊天 Prompt 配置。',
    required: false,
  },
]

const BOT_FIELDS: FieldSchema[] = [
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
    name: 'platforms',
    type: 'array',
    label: { zh_CN: '其他平台' },
    description: '其他平台账号，格式为 platform:账号。',
    required: false,
    items: { type: 'string' },
    'x-widget': 'custom',
  },
]

function domain(fields: FieldSchema[], extra: Partial<ConfigSchema> = {}): ConfigSchema {
  return { className: 'X', classDoc: '', fields, ...extra }
}

const SCHEMA: ConfigSchema = {
  className: 'Config',
  classDoc: '麦麦配置',
  fields: [],
  nested: {
    bot: domain(BOT_FIELDS, { uiLabel: '基础', uiOrder: 10 }),
    chat: domain(CHAT_FIELDS, { uiLabel: '聊天', uiOrder: 20 }),
    agent_autonomy: domain(AGENT_AUTONOMY_FIELDS, {
      uiLabel: '智能体自主性',
      uiOrder: 52,
    }),
    agent_interaction: domain([], { uiLabel: '智能体交互', uiOrder: 51 }),
    a_memorix: {
      className: 'AMemorix',
      classDoc: '',
      fields: [],
      uiLabel: '记忆',
      nested: {
        integration: domain([
          {
            name: 'memory_query_default_limit',
            type: 'integer',
            label: { zh_CN: '记忆查询默认条数' },
            description: '',
            required: false,
            default: 3,
            minValue: 1,
            maxValue: 20,
          },
        ]),
      },
    },
    // 故意留一个未接入的域（验证"其余 N 个域未接入"的计数）
    // （用 watchdog 这种真实存在但本批没接的名字）
  },
}
SCHEMA.nested = {
  ...SCHEMA.nested,
  watchdog: domain([], { uiLabel: '看门狗', uiOrder: 70 }),
}

const CONFIG = {
  bot: { nickname: '麦麦' },
  chat: { mid_term_memory_lenth: 10, ascii_column_width: 48 },
  agent_autonomy: { enabled: true, max_active_agents: 13, interjection_intent_threshold: 60 },
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
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'zh-CN' } }),
}))

vi.mock('../../hooks', () => ({
  registerAllConfigHooks: vi.fn(),
}))

import { getBotConfig, getBotConfigRaw, getBotConfigSchema } from '@/lib/config-api'

function inputOf(name: string): HTMLInputElement {
  const control = screen.getByTestId(`field-${name}`).querySelector('input')
  if (!(control instanceof HTMLInputElement)) {
    throw new Error(`字段 ${name} 未渲染 input`)
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

async function switchTo(domainPath: string) {
  fireEvent.click(screen.getByTestId(`wired-domain-${domainPath}`))
  await waitFor(() =>
    expect(screen.getByTestId('wired-domain-form')).toHaveAttribute('data-domain-path', domainPath),
  )
}

beforeEach(() => {
  vi.mocked(getBotConfig).mockResolvedValue(CONFIG)
  vi.mocked(getBotConfigSchema).mockResolvedValue(SCHEMA)
  vi.mocked(getBotConfigRaw).mockResolvedValue('')
})

describe('(a)-⑤ · 核心判据：约束在 UI 上真拦住（真实字段）', () => {
  it('`agent_autonomy.max_active_agents`（真实 2..20）：真填 999 ⇒ 看到可读提示', async () => {
    await openDetailMode()
    await switchTo('agent_autonomy')

    expect(screen.queryByTestId('field-error-max_active_agents')).not.toBeInTheDocument()
    expect(inputOf('max_active_agents')).toHaveValue(13)

    fireEvent.change(inputOf('max_active_agents'), { target: { value: '999' } })

    expect(screen.getByTestId('field-error-max_active_agents')).toHaveTextContent('值不能大于 20')
    expect(inputOf('max_active_agents')).toHaveAttribute('aria-invalid', 'true')
  })

  it('同一个字段：填 1 ⇒ 下界提示；填 2 / 20 ⇒ 含边界无提示', async () => {
    await openDetailMode()
    await switchTo('agent_autonomy')

    fireEvent.change(inputOf('max_active_agents'), { target: { value: '1' } })
    expect(screen.getByTestId('field-error-max_active_agents')).toHaveTextContent('值不能小于 2')

    fireEvent.change(inputOf('max_active_agents'), { target: { value: '2' } })
    expect(screen.queryByTestId('field-error-max_active_agents')).not.toBeInTheDocument()

    fireEvent.change(inputOf('max_active_agents'), { target: { value: '20' } })
    expect(screen.queryByTestId('field-error-max_active_agents')).not.toBeInTheDocument()
  })

  it('真实 `minValue: 0` 字段（interjection_intent_threshold 0..100）：-1 越界、0 合法', async () => {
    await openDetailMode()
    await switchTo('agent_autonomy')

    fireEvent.change(inputOf('interjection_intent_threshold'), { target: { value: '-1' } })
    expect(screen.getByTestId('field-error-interjection_intent_threshold')).toHaveTextContent(
      '值不能小于 0',
    )

    fireEvent.change(inputOf('interjection_intent_threshold'), { target: { value: '0' } })
    expect(
      screen.queryByTestId('field-error-interjection_intent_threshold'),
    ).not.toBeInTheDocument()
  })

  it('第二个域同样生效（chat.ascii_column_width 32..80）⇒ 不是"只有一个域能 work"', async () => {
    await openDetailMode()
    await switchTo('chat')

    fireEvent.change(inputOf('ascii_column_width'), { target: { value: '31' } })
    expect(screen.getByTestId('field-error-ascii_column_width')).toHaveTextContent('值不能小于 32')

    fireEvent.change(inputOf('ascii_column_width'), { target: { value: '80' } })
    expect(screen.queryByTestId('field-error-ascii_column_width')).not.toBeInTheDocument()
  })
})

describe('(a)-⑤ · 域切换与草稿', () => {
  it('默认落在「基础」（bot，uiOrder 最小）；点击后切到对应域', async () => {
    await openDetailMode()

    expect(screen.getByTestId('wired-domain-form')).toHaveAttribute('data-domain-path', 'bot')
    expect(screen.getByTestId('wired-domain-bot')).toHaveAttribute('data-active', 'true')

    await switchTo('agent_autonomy')

    expect(screen.getByTestId('wired-domain-agent_autonomy')).toHaveAttribute('data-active', 'true')
    expect(screen.getByTestId('wired-domain-bot')).toHaveAttribute('data-active', 'false')
    // 字段确实换了域
    expect(screen.getByTestId('field-max_active_agents')).toBeInTheDocument()
    expect(screen.queryByTestId('field-nickname')).not.toBeInTheDocument()
  })

  it('嵌套域（a_memorix.integration）也能切换并渲染', async () => {
    await openDetailMode()
    await switchTo('a_memorix.integration')
    expect(screen.getByTestId('field-memory_query_default_limit')).toBeInTheDocument()
  })

  it('编辑进 state（受控往返）：切走再切回，同一域内的编辑仍在', async () => {
    await openDetailMode()
    await switchTo('agent_autonomy')

    fireEvent.change(inputOf('max_active_agents'), { target: { value: '7' } })
    expect(inputOf('max_active_agents')).toHaveValue(7)

    await switchTo('chat')
    await switchTo('agent_autonomy')

    expect(inputOf('max_active_agents')).toHaveValue(7)
  })

  it('如实报出未接入的域数（其余 N 个域本批未接入）', async () => {
    await openDetailMode()
    // 夹具里 8 个域节点：bot/chat/agent_autonomy/agent_interaction/a_memorix/a_memorix.integration/watchdog
    // = 7 个节点，接入 5 个（bot/chat/agent_autonomy/agent_interaction/a_memorix.integration）
    expect(screen.getByTestId('unwired-domain-count')).toHaveTextContent('其余 2 个域本批未接入')
  })
})

describe('(a)-⑤ · 异形字段与非约束字段', () => {
  it('object 字段**显式不渲染**并如实报出（不静默兜底）', async () => {
    await openDetailMode()
    await switchTo('chat')

    expect(screen.queryByTestId('field-reply_timing')).not.toBeInTheDocument()
    expect(screen.queryByTestId('field-reply_style')).not.toBeInTheDocument()
    expect(screen.getByTestId('domain-skipped-fields')).toHaveTextContent('未渲染 2 个字段')
    expect(screen.getByTestId('domain-skipped-fields')).toHaveTextContent('reply_timing')
    expect(screen.getByTestId('domain-skipped-fields')).toHaveTextContent('reply_style')
  })

  it('array + x-widget:custom 字段同样不渲染（bot.platforms）', async () => {
    await openDetailMode()
    expect(screen.queryByTestId('field-platforms')).not.toBeInTheDocument()
    expect(screen.getByTestId('domain-skipped-fields')).toHaveTextContent('platforms')
    expect(screen.getByTestId('field-nickname')).toBeInTheDocument()
  })

  it('advanced 字段默认不渲染（agent_autonomy.speaker_tag_format）', async () => {
    await openDetailMode()
    await switchTo('agent_autonomy')
    expect(screen.queryByTestId('field-speaker_tag_format')).not.toBeInTheDocument()
  })

  it('无约束的域不产生任何提示（防误报）', async () => {
    await openDetailMode()
    expect(document.body.querySelectorAll('[data-testid^="field-error-"]')).toHaveLength(0)
  })
})
