import { describe, expect, it } from 'vitest'

import type { PluginInfo } from '@/features/plugin/shared/types'
import type { PluginManifest } from '@/types/plugin'
import { countFilteredPlugins, filterPlugins } from '../use-plugin-filter'

function makePlugin(
  overrides: { id: string } & Partial<Omit<PluginInfo, 'manifest'>> & {
    manifest?: Partial<PluginManifest>
  },
): PluginInfo {
  const { manifest: manifestOverride, ...rest } = overrides
  return {
    // 默认值在前、overrides 的 rest 在后——overrides 必须能覆盖默认值
    //（P2 踩坑：曾把 ...rest 放开头——source/installed 默认值把 overrides 覆盖——过滤测试挂）
    // id 由末尾 ...rest 提供（overrides.id 必填——无重复声明）
    manifest: {
      manifest_version: 2,
      id: overrides.id,
      name: manifestOverride?.name ?? overrides.id,
      version: '1.0.0',
      description: manifestOverride?.description ?? '',
      author: { name: 'test' },
      license: 'MIT',
      host_application: { min_version: '*' },
      keywords: manifestOverride?.keywords ?? [],
      plugin_type: manifestOverride?.plugin_type ?? 'extension',
      default_locale: 'zh_CN',
      ...manifestOverride,
    },
    downloads: 0,
    rating: 0,
    review_count: 0,
    installed: false,
    source: 'market',
    published_at: '',
    updated_at: '',
    ...rest,
  }
}

const options = {
  searchQuery: '',
  pluginTypeFilter: 'all',
  showCompatibleOnly: false,
  hideInstalledPlugins: false,
  maimaiVersion: null,
  checkPluginCompatibility: () => true,
}

describe('use-plugin-filter（过滤逻辑统一入口——R4-4a §P2-3）', () => {
  it('无过滤条件时返回全部（跳过无 manifest 与本地独有插件）', () => {
    const plugins = [
      makePlugin({ id: 'a' }),
      makePlugin({ id: 'local', source: 'local' }),
      // 真实市场数据可能缺 manifest——过滤逻辑必须跳过（类型系统表达不了——断言）
      { ...makePlugin({ id: 'no-manifest' }), manifest: undefined } as unknown as PluginInfo,
    ]
    expect(filterPlugins(plugins, options).map(p => p.id)).toEqual(['a'])
  })

  it('搜索词匹配名称/描述/关键词', () => {
    const plugins = [
      makePlugin({ id: 'chat', manifest: { name: '聊天插件', keywords: ['chat', 'im'] } }),
      makePlugin({ id: 'desc', manifest: { description: '图片生成工具', keywords: [] } }),
      makePlugin({ id: 'kw', manifest: { keywords: ['音乐'] } }),
      makePlugin({ id: 'other', manifest: { name: '无关', keywords: [] } }),
    ]
    const result = filterPlugins(plugins, { ...options, searchQuery: '图片' }).map(p => p.id)
    expect(result).toEqual(['desc'])
    const byKw = filterPlugins(plugins, { ...options, searchQuery: '音乐' }).map(p => p.id)
    expect(byKw).toEqual(['kw'])
  })

  it('类型过滤', () => {
    const plugins = [
      makePlugin({ id: 'adapter', manifest: { plugin_type: 'adapter' } }),
      makePlugin({ id: 'ext', manifest: { plugin_type: 'extension' } }),
    ]
    const result = filterPlugins(plugins, { ...options, pluginTypeFilter: 'adapter' }).map(p => p.id)
    expect(result).toEqual(['adapter'])
  })

  it('兼容性过滤（showCompatibleOnly 且具备 maimaiVersion 时才生效）', () => {
    const plugins = [makePlugin({ id: 'ok' }), makePlugin({ id: 'bad' })]
    const compat = (p: PluginInfo) => p.id === 'ok'

    // 无 maimaiVersion：兼容过滤不生效
    expect(filterPlugins(plugins, { ...options, showCompatibleOnly: true }).length).toBe(2)
    // 有 maimaiVersion + showCompatibleOnly：只留兼容项
    const result = filterPlugins(plugins, {
      ...options,
      showCompatibleOnly: true,
      maimaiVersion: { version: '1.0.0', version_major: 1, version_minor: 0, version_patch: 0 },
      checkPluginCompatibility: compat,
    }).map(p => p.id)
    expect(result).toEqual(['ok'])
  })

  it('hideInstalledPlugins 隐藏已安装插件', () => {
    const plugins = [makePlugin({ id: 'installed', installed: true }), makePlugin({ id: 'fresh' })]
    const result = filterPlugins(plugins, { ...options, hideInstalledPlugins: true }).map(p => p.id)
    expect(result).toEqual(['fresh'])
  })

  it('countFilteredPlugins 复用同一过滤逻辑', () => {
    const plugins = [makePlugin({ id: 'a' }), makePlugin({ id: 'b' }), makePlugin({ id: 'c' })]
    expect(countFilteredPlugins(plugins, options)).toBe(3)
    expect(countFilteredPlugins(plugins, { ...options, searchQuery: 'x' })).toBe(0)
  })
})
