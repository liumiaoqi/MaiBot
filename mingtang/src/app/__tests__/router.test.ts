import { describe, it, expect } from 'vitest'
import {
  routeDefinitions,
  ROUTE_COUNT,
  ROUTE_DOMAINS,
  getRoutesByDomain,
  type RouteDomain,
} from '../route-definitions'

describe('R2-1-1：36 页路由表登记（R1 的 35 + /appearance）', () => {
  it('路由总数 = 36', () => {
    expect(ROUTE_COUNT).toBe(36)
    expect(routeDefinitions).toHaveLength(36)
  })

  it('8 功能域全部覆盖', () => {
    expect(ROUTE_DOMAINS).toHaveLength(8)
    const domains = new Set(routeDefinitions.map((r) => r.domain))
    expect(domains.size).toBe(8)
    ROUTE_DOMAINS.forEach((d) => {
      expect(domains.has(d)).toBe(true)
    })
  })

  it('各域页面数符合蓝皮书 §一（config 域 R2 新增 /appearance = 9 页）', () => {
    expect(getRoutesByDomain('config')).toHaveLength(9)
    expect(getRoutesByDomain('chat')).toHaveLength(2)
    expect(getRoutesByDomain('memory')).toHaveLength(3)
    expect(getRoutesByDomain('resource')).toHaveLength(4)
    expect(getRoutesByDomain('monitor')).toHaveLength(7)
    expect(getRoutesByDomain('agent')).toHaveLength(2)
    expect(getRoutesByDomain('plugin')).toHaveLength(4)
    expect(getRoutesByDomain('home')).toHaveLength(5)
  })

  it('每个路由有唯一 id', () => {
    const ids = routeDefinitions.map((r) => r.id)
    const uniqueIds = new Set(ids)
    expect(uniqueIds.size).toBe(ids.length)
  })

  it('每个路由有非空 path 和 pageName', () => {
    routeDefinitions.forEach((r) => {
      expect(r.path).toBeTruthy()
      expect(r.pageName).toBeTruthy()
      expect(r.domain).toBeTruthy()
    })
  })

  it('路由路径与 dashboard 对齐（C-2）', () => {
    const dashboardPaths = [
      '/config/bot',
      '/config/model',
      '/config/prompts',
      '/mcp-settings',
      '/model-presets',
      '/config/prompt-generator',
      '/config/pack-market',
      '/config/pack-market/$packId',
      '/appearance',
      '/chat',
      '/chat-management',
      '/reasoning-process',
      '/resource/knowledge-graph',
      '/focus',
      '/resource/emoji',
      '/resource/expression',
      '/resource/jargon',
      '/resource/knowledge-base',
      '/deepseek-monitor',
      '/emotion-monitor',
      '/relationship-monitor',
      '/subagent-monitor',
      '/maisaka-monitor',
      '/system-monitor',
      '/logs',
      '/agents',
      '/resource/person',
      '/plugins',
      '/plugin-config',
      '/plugins/$pluginId',
      '/plugin-mirrors',
      '/',
      '/setup',
      '/survey/webui-feedback',
      '/survey/maibot-feedback',
      '*',
    ]
    expect(dashboardPaths).toHaveLength(36)

    const routePaths = routeDefinitions.map((r) => r.path)
    dashboardPaths.forEach((p) => {
      expect(routePaths).toContain(p)
    })
  })

  it('36 页按蓝皮书 §一 8 域归属 features/<domain>/', () => {
    const domainPages: Record<RouteDomain, string[]> = {
      config: ['config/bot', 'config/model', 'config/prompts', 'config/mcp-settings', 'config/model-presets', 'config/prompt-generator', 'config/pack-market', 'config/pack-detail', 'config/appearance'],
      chat: ['chat/chat', 'chat/chat-management'],
      memory: ['memory/reasoning-process', 'memory/memory', 'memory/focus'],
      resource: ['resource/emoji', 'resource/expression', 'resource/jargon', 'resource/knowledge-base'],
      monitor: ['monitor/deepseek', 'monitor/emotion', 'monitor/relationship', 'monitor/subagent', 'monitor/maisaka', 'monitor/system', 'monitor/logs'],
      agent: ['agent/agent', 'agent/person'],
      plugin: ['plugin/plugins', 'plugin/plugin-config', 'plugin/plugin-detail', 'plugin/plugin-mirrors'],
      home: ['home/home', 'home/setup', 'home/survey-webui-feedback', 'home/survey-maibot-feedback', 'home/404'],
    }

    Object.entries(domainPages).forEach(([domain, ids]) => {
      const routes = getRoutesByDomain(domain as RouteDomain)
      const routeIds = routes.map((r) => r.id)
      expect(routeIds.sort()).toEqual(ids.sort())
    })
  })
})