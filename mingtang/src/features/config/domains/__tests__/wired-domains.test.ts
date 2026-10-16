import { describe, it, expect } from 'vitest'
import {
  WIRED_DOMAIN_PATHS,
  countAllDomains,
  listWiredDomains,
  prepareDomainForm,
  readDomainValues,
  resolveDomainLabel,
  resolveDomainSchema,
} from '../wired-domains'
import type { ConfigSchema, FieldSchema } from '@/types/config-schema'

function field(partial: Partial<FieldSchema> & Pick<FieldSchema, 'name' | 'type'>): FieldSchema {
  return { label: partial.name, description: '', required: false, ...partial }
}

function domain(fields: FieldSchema[], extra: Partial<ConfigSchema> = {}): ConfigSchema {
  return { className: 'X', classDoc: '', fields, ...extra }
}

describe('(a)-⑤ · 域收敛：只留能安全渲染的标量字段', () => {
  it('array / object / x-widget:custom 一律剔除，并给出原因', () => {
    const source = domain([
      field({ name: 'a_int', type: 'integer', minValue: 1, maxValue: 9 }),
      field({ name: 'b_arr', type: 'array', items: { type: 'string' } }),
      field({ name: 'c_obj', type: 'object' }),
      field({ name: 'd_custom', type: 'string', 'x-widget': 'custom' }),
      field({ name: 'e_bool', type: 'boolean' }),
    ])

    const { schema, skipped } = prepareDomainForm(source)

    expect(schema.fields.map((each) => each.name)).toEqual(['a_int', 'e_bool'])
    expect(skipped).toEqual([
      { name: 'b_arr', reason: 'array' },
      { name: 'c_obj', reason: 'object' },
      { name: 'd_custom', reason: 'custom-widget' },
    ])
    // 原 schema 不被改（只换 fields 数组）
    expect(source.fields).toHaveLength(5)
  })

  it('字段顺序保持（渲染顺序 = 后端给的顺序）', () => {
    const source = domain([
      field({ name: 'z', type: 'integer' }),
      field({ name: 'm', type: 'integer' }),
      field({ name: 'a', type: 'integer' }),
    ])
    expect(prepareDomainForm(source).schema.fields.map((f) => f.name)).toEqual(['z', 'm', 'a'])
  })

  it('纯标量域原样通过（skipped 为空）', () => {
    const source = domain([field({ name: 'x', type: 'number', minValue: 0 })])
    const { schema, skipped } = prepareDomainForm(source)
    expect(schema.fields).toHaveLength(1)
    expect(skipped).toEqual([])
  })

  it('`x-widget: custom` 优先按"控件不认识"归类（即便类型是标量）', () => {
    // 真实存在的形状：bot.platforms 是 array+custom；这里构造标量+custom 的边界
    const source = domain([field({ name: 'odd', type: 'string', 'x-widget': 'custom' })])
    expect(prepareDomainForm(source).skipped).toEqual([{ name: 'odd', reason: 'custom-widget' }])
  })
})

describe('(a)-⑤ · 域路径解析（复用接缝的路径代数）', () => {
  const root: ConfigSchema = {
    className: 'Config',
    classDoc: '',
    fields: [],
    nested: {
      bot: domain([field({ name: 'nickname', type: 'string' })], { uiLabel: '基础' }),
      a_memorix: {
        className: 'AMemorix',
        classDoc: '',
        fields: [],
        uiLabel: '记忆',
        nested: {
          integration: domain([field({ name: 'x', type: 'integer' })], {
            uiLabel: '集成',
          }),
        },
      },
    },
  }

  it('顶层域与嵌套域都能取到 schema', () => {
    expect(resolveDomainSchema(root, 'bot')?.fields[0].name).toBe('nickname')
    expect(resolveDomainSchema(root, 'a_memorix.integration')?.fields[0].name).toBe('x')
  })

  it('不存在的域 ⇒ undefined（不抛；界面据此显示"该域不存在"）', () => {
    expect(resolveDomainSchema(root, 'nope')).toBeUndefined()
    expect(resolveDomainSchema(root, 'a_memorix.nope')).toBeUndefined()
  })

  it('域路径带下标 ⇒ 明确报错（域不是数组元素，不猜）', () => {
    expect(() => resolveDomainSchema(root, 'a[0]')).toThrow(/不能含数组下标/)
  })

  it('readDomainValues：按同一条路径取嵌套值；缺失/类型不符一律空字典', () => {
    const config = { bot: { nickname: '麦麦' }, a_memorix: { integration: { x: 1 } } }
    expect(readDomainValues(config, 'bot')).toEqual({ nickname: '麦麦' })
    expect(readDomainValues(config, 'a_memorix.integration')).toEqual({ x: 1 })
    expect(readDomainValues(config, 'a_memorix.missing')).toEqual({})
    expect(readDomainValues(config, 'bot.nickname')).toEqual({})
    expect(readDomainValues(undefined, 'bot')).toEqual({})
    expect(readDomainValues({ bot: [] }, 'bot')).toEqual({})
  })
})

describe('(a)-⑤ · 域显示名（后端 label 优先，缺失时按祖先组合）', () => {
  it('自带 uiLabel ⇒ 原样用它（后端给的是**纯字符串**，不是 {zh_CN:…} 字典）', () => {
    const root: ConfigSchema = {
      className: 'Config',
      classDoc: '',
      fields: [],
      nested: { chat: domain([], { uiLabel: '聊天' }) },
    }
    expect(resolveDomainLabel(root, 'chat')).toBe('聊天')
  })

  it('自身没有 uiLabel ⇒ 用最近有名字的祖先 + 叶子键名（不硬编码中文）', () => {
    const root: ConfigSchema = {
      className: 'Config',
      classDoc: '',
      fields: [],
      nested: {
        a_memorix: {
          className: 'AMemorix',
          classDoc: '',
          fields: [],
          uiLabel: '记忆',
          nested: { integration: domain([]) },
        },
      },
    }
    // 实测就是这个形状：a_memorix 有「记忆」，a_memorix.integration 没有 uiLabel
    expect(resolveDomainLabel(root, 'a_memorix.integration')).toBe('记忆 · integration')
  })

  it('整条链都没有名字 ⇒ 退回原始路径', () => {
    const root: ConfigSchema = { className: 'Config', classDoc: '', fields: [], nested: { x: { className: 'X', classDoc: '', fields: [], nested: { y: domain([]) } } } }
    expect(resolveDomainLabel(root, 'x.y')).toBe('x.y')
  })
})

describe('(a)-⑤ · 接入清单与域总数', () => {
  it('按后端 uiOrder 排序；无 uiOrder 的排最后', () => {
    const root: ConfigSchema = {
      className: 'Config',
      classDoc: '',
      fields: [],
      nested: {
        agent_autonomy: domain([field({ name: 'a', type: 'integer' })], { uiOrder: 52 }),
        bot: domain([field({ name: 'b', type: 'string' })], { uiOrder: 10 }),
        chat: domain([field({ name: 'c', type: 'integer' })], { uiOrder: 20 }),
        a_memorix: {
          className: 'A',
          classDoc: '',
          fields: [],
          nested: { integration: domain([field({ name: 'd', type: 'integer' })]) },
        },
      },
    }

    const list = listWiredDomains(root)
    expect(list.map((each) => each.path)).toEqual([
      'bot',
      'chat',
      'agent_autonomy',
      'a_memorix.integration', // 无 uiOrder ⇒ 最后
    ])
    expect(list[0].uiOrder).toBe(10)
    expect(list[3].uiOrder).toBeNull()
  })

  it('只列 schema 里真实存在的接入域（不存在的不列出）', () => {
    const root: ConfigSchema = {
      className: 'Config',
      classDoc: '',
      fields: [],
      nested: { bot: domain([field({ name: 'b', type: 'string' })]) },
    }
    expect(listWiredDomains(root).map((each) => each.path)).toEqual(['bot'])
    // 接入清单里确实还有其他域（只是这份 schema 没有）
    expect(WIRED_DOMAIN_PATHS.length).toBeGreaterThan(1)
  })

  it('renderableCount / skippedCount 如实反映收敛结果', () => {
    const root: ConfigSchema = {
      className: 'Config',
      classDoc: '',
      fields: [],
      nested: {
        chat: domain([
          field({ name: 'keep', type: 'integer' }),
          field({ name: 'drop1', type: 'object' }),
          field({ name: 'drop2', type: 'object' }),
        ]),
      },
    }
    const entry = listWiredDomains(root)[0]
    expect(entry.renderableCount).toBe(1)
    expect(entry.skippedCount).toBe(2)
  })

  it('countAllDomains 数的是全部域节点（用来报"其余 N 个未接入"）', () => {
    const root: ConfigSchema = {
      className: 'Config',
      classDoc: '',
      fields: [],
      nested: {
        a: { className: 'A', classDoc: '', fields: [], nested: { b: domain([]) } },
        c: domain([]),
      },
    }
    expect(countAllDomains(root)).toBe(3)
  })
})
