import {
  createRouter,
  createRootRoute,
  createRoute,
  Outlet,
} from '@tanstack/react-router'
import { Placeholder } from '../components/biz/placeholder'
import { Layout } from './layout'
import { routeDefinitions, type RouteDefinition } from './route-definitions'

// 根路由
const rootRoute = createRootRoute({
  component: () => <Outlet />,
})

// 受保护路由（带 Layout）
const protectedRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'protected',
  component: () => (
    <Layout>
      <Outlet />
    </Layout>
  ),
})

/** 根据路由定义创建占位路由 */
function createPlaceholderRoute(def: RouteDefinition) {
  const component = () => (
    <Placeholder pageName={def.pageName} domain={def.domain} />
  )

  // 404 路由挂在 rootRoute 下
  if (def.path === '*') {
    return createRoute({
      getParentRoute: () => rootRoute,
      path: def.path,
      component,
    })
  }

  // setup 路由挂在 rootRoute 下（无 Layout——与 dashboard 对齐）
  if (def.path === '/setup') {
    return createRoute({
      getParentRoute: () => rootRoute,
      path: def.path,
      component,
    })
  }

  // 其余路由挂在 protectedRoute 下
  return createRoute({
    getParentRoute: () => protectedRoute,
    path: def.path,
    component,
  })
}

// 创建 34 页路由
const routes = routeDefinitions.map(createPlaceholderRoute)

// 提取各路由引用（按定义顺序）
const [
  configBotRoute,
  configModelRoute,
  configPromptsRoute,
  configMcpSettingsRoute,
  configModelPresetsRoute,
  configPromptGeneratorRoute,
  configPackMarketRoute,
  configPackDetailRoute,
  chatRoute,
  chatManagementRoute,
  memoryReasoningProcessRoute,
  memoryMemoryRoute,
  memoryFocusRoute,
  resourceEmojiRoute,
  resourceExpressionRoute,
  resourceJargonRoute,
  resourceKnowledgeBaseRoute,
  monitorDeepseekRoute,
  monitorEmotionRoute,
  monitorRelationshipRoute,
  monitorSubagentRoute,
  monitorSystemRoute,
  monitorLogsRoute,
  agentAgentRoute,
  agentPersonRoute,
  pluginPluginsRoute,
  pluginConfigRoute,
  pluginDetailRoute,
  pluginMirrorsRoute,
  homeHomeRoute,
  homeSetupRoute,
  homeSurveyWebuiRoute,
  homeSurveyMaibotRoute,
  homeNotFoundRoute,
] = routes

// 路由树
const routeTree = rootRoute.addChildren([
  homeSetupRoute,
  protectedRoute.addChildren([
    configBotRoute,
    configModelRoute,
    configPromptsRoute,
    configMcpSettingsRoute,
    configModelPresetsRoute,
    configPromptGeneratorRoute,
    configPackMarketRoute,
    configPackDetailRoute,
    chatRoute,
    chatManagementRoute,
    memoryReasoningProcessRoute,
    memoryMemoryRoute,
    memoryFocusRoute,
    resourceEmojiRoute,
    resourceExpressionRoute,
    resourceJargonRoute,
    resourceKnowledgeBaseRoute,
    monitorDeepseekRoute,
    monitorEmotionRoute,
    monitorRelationshipRoute,
    monitorSubagentRoute,
    monitorSystemRoute,
    monitorLogsRoute,
    agentAgentRoute,
    agentPersonRoute,
    pluginPluginsRoute,
    pluginConfigRoute,
    pluginDetailRoute,
    pluginMirrorsRoute,
    homeHomeRoute,
    homeSurveyWebuiRoute,
    homeSurveyMaibotRoute,
  ]),
  homeNotFoundRoute,
])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
