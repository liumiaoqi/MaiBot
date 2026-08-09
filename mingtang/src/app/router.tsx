import {
  createRouter,
  createRootRoute,
  createRoute,
  Outlet,
} from '@tanstack/react-router'
import { Placeholder } from '../components/biz/placeholder'
import { Layout } from './layout'
import { routeDefinitions, type RouteDefinition } from './route-definitions'
import { AppearancePage } from '../features/config/appearance'
import { BotConfigPage } from '../features/config/bot'
import { ModelConfigPage } from '../features/config/model'
import { PromptManagementPage } from '../features/config/prompts'
import { MCPSettingsPage } from '../features/config/mcp-settings'
import { ModelPresetsPage } from '../features/config/model-presets'
import { PromptGeneratorPage } from '../features/config/prompt-generator'
import { PackMarketPage } from '../features/config/pack-market'
import { PackDetailPage } from '../features/config/pack-detail'
import { ChatPage } from '../features/chat'
import { ChatManagementPage } from '../features/chat/chat-management'

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

/** config 域 9 页 + chat 域 1 页使用实际页面组件，其余域占位 */
const actualPageComponents: Record<string, () => React.ReactElement> = {
  '/config/bot': () => <BotConfigPage />,
  '/config/model': () => <ModelConfigPage />,
  '/config/prompts': () => <PromptManagementPage />,
  '/mcp-settings': () => <MCPSettingsPage />,
  '/model-presets': () => <ModelPresetsPage />,
  '/config/prompt-generator': () => <PromptGeneratorPage />,
  '/config/pack-market': () => <PackMarketPage />,
  '/config/pack-market/$packId': () => <PackDetailPage />,
  '/appearance': () => <AppearancePage />,
  '/chat': () => <ChatPage />,
  '/chat-management': () => <ChatManagementPage />,
}

/** 根据路由定义创建路由（config 域 9 页使用实际组件，其余占位） */
function createPlaceholderRoute(def: RouteDefinition) {
  const actualComponent = actualPageComponents[def.path]
  const component = def.path in actualPageComponents
    ? actualComponent
    : () => (
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

// 创建 36 页路由
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
  configAppearanceRoute,
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
    configAppearanceRoute,
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
