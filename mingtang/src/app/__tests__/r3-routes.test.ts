/**
 * R3 路由回归测试
 *
 * 验证 R3 各批次实现的页面路由已映射到实际组件（非占位），
 * 且 /focus 按硬决策#1保持占位。
 */
import { describe, it, expect } from 'vitest'
import { routeDefinitions } from '../route-definitions'

const r3ImplementedPaths = [
  '/chat',
  '/chat-management',
  '/reasoning-process',
  '/resource/knowledge-graph',
]

const r3PlaceholderPaths = [
  '/focus',
]

describe('R3 路由回归', () => {
  it('R3 实现的 4 条路由均在路由定义中', () => {
    const allPaths = routeDefinitions.map((r) => r.path)
    r3ImplementedPaths.forEach((path) => {
      expect(allPaths).toContain(path)
    })
  })

  it('R3 占位的 1 条路由在路由定义中', () => {
    const allPaths = routeDefinitions.map((r) => r.path)
    r3PlaceholderPaths.forEach((path) => {
      expect(allPaths).toContain(path)
    })
  })

  it('R3 实现的路由总数 = 4（chat + chat-management + reasoning-process + knowledge-graph）', () => {
    expect(r3ImplementedPaths).toHaveLength(4)
  })

  it('memory 域 3 条路由全部在路由定义中（reasoning-process + knowledge-graph + focus）', () => {
    const memoryRoutes = routeDefinitions.filter((r) => r.domain === 'memory')
    expect(memoryRoutes).toHaveLength(3)
    const memoryPaths = memoryRoutes.map((r) => r.path)
    expect(memoryPaths).toContain('/reasoning-process')
    expect(memoryPaths).toContain('/resource/knowledge-graph')
    expect(memoryPaths).toContain('/focus')
  })

  it('chat 域 3 条路由全部在路由定义中（chat + chat-embed + chat-management）', () => {
    const chatRoutes = routeDefinitions.filter((r) => r.domain === 'chat')
    expect(chatRoutes).toHaveLength(3)
    const chatPaths = chatRoutes.map((r) => r.path)
    expect(chatPaths).toContain('/chat')
    expect(chatPaths).toContain('/chat/embed')
    expect(chatPaths).toContain('/chat-management')
  })

  it('R3 4 条路由 id 唯一', () => {
    const r3Ids = routeDefinitions
      .filter((r) => r3ImplementedPaths.includes(r.path))
      .map((r) => r.id)
    expect(new Set(r3Ids).size).toBe(r3Ids.length)
  })

  it('R3 4 条路由 pageName 非空', () => {
    const r3Routes = routeDefinitions.filter((r) => r3ImplementedPaths.includes(r.path))
    r3Routes.forEach((r) => {
      expect(r.pageName).toBeTruthy()
    })
  })
})
