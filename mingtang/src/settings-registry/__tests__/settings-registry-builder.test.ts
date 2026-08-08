import { describe, it, expect, beforeEach } from 'vitest'
import { buildEntriesFromSchema } from '../builder'
import { fieldHooks } from '@/lib/field-hooks'
import type { ConfigSchema } from '@/types/config-schema'

function makeSchema(overrides: Partial<ConfigSchema> = {}): ConfigSchema {
  return {
    className: 'BotConfig',
    classDoc: '机器人配置',
    fields: [
      { name: 'nickname', type: 'string', label: '昵称', description: '机器人昵称', required: true },
      { name: 'age', type: 'integer', label: '年龄', description: '机器人年龄', required: false },
    ],
    ...overrides,
  }
}

describe('R1-3-2：schema 自动登记 buildEntriesFromSchema', () => {
  beforeEach(() => {
    fieldHooks.clear()
  })

  it('单层 schema 遍历 → 每个字段生成一个 entry', () => {
    const schema = makeSchema()
    const entries = buildEntriesFromSchema(schema, 'bot', '/config/bot')
    expect(entries).toHaveLength(2)
    expect(entries[0].id).toBe('auto:bot:nickname')
    expect(entries[1].id).toBe('auto:bot:age')
  })

  it('所有条目 source 为 "auto"', () => {
    const schema = makeSchema()
    const entries = buildEntriesFromSchema(schema, 'bot', '/config/bot')
    expect(entries.every((e) => e.source === 'auto')).toBe(true)
  })

  it('条目含 fieldPath 和 schemaRef', () => {
    const schema = makeSchema()
    const entries = buildEntriesFromSchema(schema, 'bot', '/config/bot')
    expect(entries[0].fieldPath).toBe('nickname')
    expect(entries[0].schemaRef).toBe('BotConfig')
  })

  it('nested 递归 → 嵌套字段 fieldPath 含父路径', () => {
    const schema: ConfigSchema = {
      className: 'BotConfig',
      classDoc: '机器人配置',
      fields: [],
      nested: {
        personality: {
          className: 'Personality',
          classDoc: '人格设置',
          fields: [
            { name: 'nickname', type: 'string', label: '人格昵称', description: '', required: true },
          ],
        },
      },
    }
    const entries = buildEntriesFromSchema(schema, 'bot', '/config/bot')
    expect(entries).toHaveLength(1)
    expect(entries[0].fieldPath).toBe('personality.nickname')
    expect(entries[0].id).toBe('auto:bot:personality.nickname')
  })

  it('fieldHooks 中 type: "hidden" 字段 → 不生成 entry', () => {
    fieldHooks.register('secret', () => null, 'hidden')
    const schema: ConfigSchema = {
      className: 'Test',
      classDoc: '',
      fields: [
        { name: 'visible', type: 'string', label: '可见', description: '', required: true },
        { name: 'secret', type: 'string', label: '隐藏', description: '', required: false },
      ],
    }
    const entries = buildEntriesFromSchema(schema, 'bot', '/config/bot')
    expect(entries).toHaveLength(1)
    expect(entries[0].fieldPath).toBe('visible')
  })

  it('fieldHooks 中 type: "replace" 字段 → 生成 entry 且 customEditor 有值', () => {
    fieldHooks.register('custom', () => null, 'replace')
    const schema: ConfigSchema = {
      className: 'Test',
      classDoc: '',
      fields: [
        { name: 'custom', type: 'string', label: '自定义', description: '', required: true },
      ],
    }
    const entries = buildEntriesFromSchema(schema, 'bot', '/config/bot')
    expect(entries).toHaveLength(1)
    expect(entries[0].customEditor).toBe('replace')
  })

  it('keywords 构建 → 含 label / name / description / fieldPath', () => {
    const schema: ConfigSchema = {
      className: 'Test',
      classDoc: '',
      fields: [
        { name: 'nickname', type: 'string', label: '昵称', description: '机器人名字', required: true },
      ],
    }
    const entries = buildEntriesFromSchema(schema, 'bot', '/config/bot')
    const keywords = entries[0].keywords
    // label
    expect(keywords).toContain('昵称')
    // name
    expect(keywords).toContain('nickname')
    // description
    expect(keywords).toContain('机器人名字')
    // fieldPath 去空格变体
    expect(keywords).toContain('nickname')
  })

  it('keywords 含 options', () => {
    const schema: ConfigSchema = {
      className: 'Test',
      classDoc: '',
      fields: [
        { name: 'mode', type: 'select', label: '模式', description: '', required: true, options: ['chat', 'command'] },
      ],
    }
    const entries = buildEntriesFromSchema(schema, 'bot', '/config/bot')
    const keywords = entries[0].keywords
    expect(keywords).toContain('chat')
    expect(keywords).toContain('command')
  })

  it('条目 route 与传入 route 一致', () => {
    const schema = makeSchema()
    const entries = buildEntriesFromSchema(schema, 'bot', '/config/bot')
    expect(entries.every((e) => e.route === '/config/bot')).toBe(true)
  })
})