import { describe, it, expect } from 'vitest'
import {
  diffToMutateOps,
  entriesToNested,
  flattenConfig,
  nestedToEntries,
  unflattenConfig,
} from '../config-adapter'
import { ConfigPathFormatError, formatConfigPath, isSecretMarker, parseConfigPath } from '../config-paths'
import type { ConfigReadEntry } from '@/lib/config-api'
import modelConfigFixture from './fixtures/model-config.json'

/**
 * 真配置夹具：**逐字取自后端已存储的 model 平面**
 * （`config_store.read_snapshot('model')` → `to_plain`，2026-10-16 于容器内 dump）。
 *
 * ⚠️ 两处如实说明：
 * 1. **已声明秘密（`api_providers[].api_key`）的值被换成哑值** `sk-FIXTURE-NOT-A-REAL-KEY`
 *    ——真密钥绝不进仓。
 * 2. 这里存的是**文件里的形态**（嵌套、含明文哑值），不是接缝读的响应形态
 *    （接缝会把秘密叶换成三态标记）——往返判据要的是前者。
 *
 * 顺带记一条**不会写进回执以外的判断**：bot 平面的真配置里有 `qq_account`（真 QQ 号）
 * 与 lmq 自己写的人格文本 ⇒ 那个平面**不能**照抄进夹具。所以"真配置往返"这条用 model 平面，
 * 它的结构面（数组套表 / 空表 / 空数组 / 深一层嵌套 / 浮点 / 布尔）已经足够当判据。
 */
const REAL_CONFIG = modelConfigFixture as Record<string, unknown>

describe('A · 路径代数（镜像后端 config_paths.py）', () => {
  it('parse → format 往返一致', () => {
    const paths = [
      'nickname',
      'chat.max_context_size',
      'api_providers[0].api_key',
      'api_providers[12].name',
      'a.b[0].c[1].d',
      'maim_message.auth_token[0]',
    ]
    for (const path of paths) {
      expect(formatConfigPath(parseConfigPath(path))).toBe(path)
    }
  })

  it('解析出的 token 形状正确（键为 string、下标为 number）', () => {
    expect(parseConfigPath('api_providers[1].api_key')).toEqual(['api_providers', 1, 'api_key'])
    expect(parseConfigPath('  spaced.key  ')).toEqual(['spaced', 'key'])
  })

  it('非法路径逐条拒绝（与后端同一批判据）', () => {
    const invalids = [
      '',
      '   ',
      'a..b',
      'a.',
      '.a',
      'a[',
      'a[]',
      'a[x]',
      'a[1',
      '[0].a',
      'a[0]b',
      'a b',
    ]
    for (const path of invalids) {
      expect(() => parseConfigPath(path), `应拒绝：${JSON.stringify(path)}`).toThrow(
        ConfigPathFormatError,
      )
    }
  })

  it('format 拒绝以下标开头的 token 序列', () => {
    expect(() => formatConfigPath([0, 'a'])).toThrow(ConfigPathFormatError)
  })

  it('isSecretMarker：认本版与遗留两种形状，拒绝"恰好长成占位"的普通表', () => {
    expect(isSecretMarker({ $secret: true, path: 'x', set: true, kind: 'literal' })).toBe(true)
    // 遗留形状（老客户端手里的占位不该因为服务端升级就作废）
    expect(isSecretMarker({ path: 'x', set: false })).toBe(true)
    // 允许多余键（前端可以附加展示信息）
    expect(isSecretMarker({ $secret: true, path: 'x', set: true, extra: 1 })).toBe(true)

    // 普通数据表：类型不对就不认（宁可不认，也别把用户的表当占位吃掉）
    expect(isSecretMarker({ path: 1, set: true })).toBe(false)
    expect(isSecretMarker({ path: 'x', set: 'yes' })).toBe(false)
    expect(isSecretMarker({ $secret: false, path: 'x', set: true })).toBe(false)
    expect(isSecretMarker(null)).toBe(false)
    expect(isSecretMarker(['x'])).toBe(false)
    expect(isSecretMarker('x')).toBe(false)
  })
})

describe('A · 适配层：嵌套 ⇄ 扁平', () => {
  it('真配置往返**逐字符一致**（这是 A 的头号判据）', () => {
    const leaves = flattenConfig(REAL_CONFIG)
    const restored = unflattenConfig(leaves)

    expect(leaves.length).toBeGreaterThan(40)
    expect(JSON.stringify(restored)).toBe(JSON.stringify(REAL_CONFIG))
  })

  it('真配置：数组顺序保持（数组套表也不例外）', () => {
    const leaves = flattenConfig(REAL_CONFIG)
    const paths = leaves.map((leaf) => leaf.path)

    expect(paths).toContain('api_providers[0].name')
    expect(paths).toContain('api_providers[1].name')
    expect(paths.indexOf('api_providers[0].name')).toBeLessThan(
      paths.indexOf('api_providers[1].name'),
    )

    const restored = unflattenConfig(leaves) as {
      api_providers: Array<{ name: string }>
      models: Array<{ name: string }>
    }
    expect(restored.api_providers.map((p) => p.name)).toEqual(['DeepSeek', 'Alibaba'])
    expect(restored.models[0].name).toBe('deepseek-v4-pro-think')
  })

  it('空表与空数组也是"叶"（丢了它们往返就失真）', () => {
    const sample = { a: {}, b: [], c: { d: {} } }
    const paths = flattenConfig(sample).map((leaf) => leaf.path)
    expect(paths).toEqual(['a', 'b', 'c.d'])
    expect(JSON.stringify(unflattenConfig(flattenConfig(sample)))).toBe(JSON.stringify(sample))
  })

  it('`null` 与"缺失"不混同（本仓老坑：MISSING ≠ None）', () => {
    const withNull = { a: null, b: 1 }
    const withoutKey = { b: 1 }

    expect(flattenConfig(withNull).map((leaf) => leaf.path)).toEqual(['a', 'b'])
    expect(flattenConfig(withoutKey).map((leaf) => leaf.path)).toEqual(['b'])

    const restoredNull = unflattenConfig(flattenConfig(withNull))
    const restoredMissing = unflattenConfig(flattenConfig(withoutKey))
    expect('a' in restoredNull).toBe(true)
    expect(restoredNull.a).toBeNull()
    expect('a' in restoredMissing).toBe(false)
    expect(JSON.stringify(restoredNull)).toBe(JSON.stringify(withNull))
  })

  it('深一层 + 下标混排往返一致', () => {
    const sample = { a: { b: [{ c: [1, 2] }, { c: [] }] }, z: 'tail' }
    expect(JSON.stringify(unflattenConfig(flattenConfig(sample)))).toBe(JSON.stringify(sample))
    expect(flattenConfig(sample).map((leaf) => leaf.path)).toEqual([
      'a.b[0].c[0]',
      'a.b[0].c[1]',
      'a.b[1].c',
      'z',
    ])
  })

  it('不做空洞填充：手造出跳过中间下标的叶 ⇒ 明确报错', () => {
    expect(() => unflattenConfig([{ path: 'a[2]', value: 1 }])).toThrow(/空洞填充/)
  })

  it('只做形状转换，不做业务校验 / 不纠正类型', () => {
    // 值违反 schema 语义（该是整数的位置放字符串）也原样通过——校验是后端的事
    const odd = { max_tokens: 'not-a-number', temperature: { nested: [] } }
    expect(JSON.stringify(unflattenConfig(flattenConfig(odd)))).toBe(JSON.stringify(odd))
    expect(nestedToEntries(REAL_CONFIG).length).toBe(flattenConfig(REAL_CONFIG).length)
  })
})

describe('A · 读条目 ⇄ 嵌套', () => {
  it('entriesToNested 跳过秘密占位（含 set:false 的"未配置"项——它连键都不该造出来）', () => {
    const entries: ConfigReadEntry[] = [
      { path: 'nickname', value: '麦麦', inherited: false, revision: 7 },
      {
        path: 'maim_message.auth_token',
        value: { $secret: true, path: 'maim_message.auth_token', set: false },
        inherited: true,
        revision: 7,
      },
      {
        path: 'api_providers[0].api_key',
        value: { $secret: true, path: 'api_providers[0].api_key', set: true, kind: 'reference' },
        inherited: true,
        revision: 7,
      },
      { path: 'api_providers[0].name', value: 'DeepSeek', inherited: false, revision: 7 },
    ]

    const nested = entriesToNested(entries)
    expect(JSON.stringify(nested)).toBe(
      JSON.stringify({ nickname: '麦麦', api_providers: [{ name: 'DeepSeek' }] }),
    )
    // 未配置的秘密不能凭空造出键
    expect(JSON.stringify(nested)).not.toContain('auth_token')
    expect(JSON.stringify(nested)).not.toContain('api_key')
  })
})

describe('A · 差分 ⇒ 路径操作（"只发改动的点"）', () => {
  it('无改动 ⇒ 一条 op 都不发', () => {
    expect(diffToMutateOps(REAL_CONFIG, REAL_CONFIG)).toEqual([])
    expect(diffToMutateOps(structuredClone(REAL_CONFIG), REAL_CONFIG)).toEqual([])
  })

  it('真配置改一个标量 ⇒ 只发一条 op（不把整份覆盖带过来）', () => {
    const next = structuredClone(REAL_CONFIG) as { models: Array<{ price_in: number }> }
    next.models[0].price_in = 99

    const ops = diffToMutateOps(REAL_CONFIG, next)
    expect(ops).toEqual([{ op: 'set', path: 'models[0].price_in', value: 99 }])
  })

  it('改表项里的一个字段 ⇒ 同表项的其它字段（含秘密）不进 ops', () => {
    const next = structuredClone(REAL_CONFIG) as {
      api_providers: Array<{ name: string; api_key?: unknown }>
    }
    next.api_providers[0].name = 'Renamed'

    const ops = diffToMutateOps(REAL_CONFIG, next)
    expect(ops).toEqual([{ op: 'set', path: 'api_providers[0].name', value: 'Renamed' }])
    expect(JSON.stringify(ops)).not.toContain('api_key')
  })

  it('秘密占位原样回写 ⇒ 发的是占位本身（前端不拿真值，由后端认领）', () => {
    const marker = {
      $secret: true as const,
      path: 'api_providers[0].api_key',
      set: true,
      kind: 'literal' as const,
    }
    const baseline = { api_providers: [{ name: 'DeepSeek', api_key: marker }] }
    const next = { api_providers: [{ name: 'DeepSeek', api_key: marker }] }
    // 未改动 ⇒ 连占位都不发
    expect(diffToMutateOps(baseline, next)).toEqual([])

    // 整体替换表项（形状没变也会逐叶比，故这里只改 name 时才一条）
    const next2 = { api_providers: [{ name: 'X', api_key: marker }] }
    expect(diffToMutateOps(baseline, next2)).toEqual([
      { op: 'set', path: 'api_providers[0].name', value: 'X' },
    ])
  })

  it('数组变长 ⇒ 升序 set（下标==长度 ⇒ 后端走追加）', () => {
    const base = { list: ['a'] }
    const next = { list: ['a', 'b', 'c'] }
    expect(diffToMutateOps(base, next)).toEqual([
      { op: 'set', path: 'list[1]', value: 'b' },
      { op: 'set', path: 'list[2]', value: 'c' },
    ])
  })

  it('数组变短 ⇒ remove_at 降序，且 path 指容器（F8：不写 list[2]）', () => {
    const base = { list: ['a', 'b', 'c', 'd'] }
    const next = { list: ['a', 'b'] }
    expect(diffToMutateOps(base, next)).toEqual([
      { op: 'remove_at', path: 'list', index: 3 },
      { op: 'remove_at', path: 'list', index: 2 },
    ])
  })

  it('删键 ⇒ unset；`null` ⇒ 也是 unset（TOML 表达不了 null）', () => {
    const base = { a: 1, b: 2 }
    expect(diffToMutateOps(base, { a: 1 })).toEqual([{ op: 'unset', path: 'b' }])
    expect(diffToMutateOps(base, { a: 1, b: null })).toEqual([{ op: 'unset', path: 'b' }])
  })

  it('基线里本来没有的键被清空 ⇒ 不发 op（已经是继承态）', () => {
    expect(diffToMutateOps({ a: 1 }, { a: 1, b: null })).toEqual([])
    expect(diffToMutateOps({ a: 1 }, { a: 1, b: undefined })).toEqual([])
  })

  it('新增一整棵子树 ⇒ 一次 set（不逐叶下钻）', () => {
    const base = { a: 1 }
    const next = { a: 1, fresh: { x: 1, y: { z: 2 } } }
    expect(diffToMutateOps(base, next)).toEqual([
      { op: 'set', path: 'fresh', value: { x: 1, y: { z: 2 } } },
    ])
  })

  it('基线里是空表、目标是子表 ⇒ 在"基线没有的那一层"整棵 set（不逐叶下钻）', () => {
    const base = { extra_params: {} }
    const next = { extra_params: { thinking: { type: 'enabled' } } }
    // `extra_params` 两边都是表 ⇒ 继续下钻；`thinking` 基线没有 ⇒ 在那一层整棵发
    expect(diffToMutateOps(base, next)).toEqual([
      { op: 'set', path: 'extra_params.thinking', value: { type: 'enabled' } },
    ])
  })

  it('形状变了（表 ⇄ 数组）⇒ 整棵 set', () => {
    expect(diffToMutateOps({ a: { x: 1 } }, { a: [1, 2] })).toEqual([
      { op: 'set', path: 'a', value: [1, 2] },
    ])
    expect(diffToMutateOps({ a: ['x'] }, { a: { x: 1 } })).toEqual([
      { op: 'set', path: 'a', value: { x: 1 } },
    ])
  })
})
