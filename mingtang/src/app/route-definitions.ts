/** 35 页路由定义（按蓝皮书 §一 8 域归属——路径与 dashboard 对齐 C-2；R2 新增 /appearance，R4-3 砍遥测页） */

export type RouteDomain =
  | 'config'
  | 'chat'
  | 'memory'
  | 'resource'
  | 'monitor'
  | 'agent'
  | 'plugin'
  | 'home'

export interface RouteDefinition {
  /** 唯一标识（域/页面名） */
  id: string
  /** 功能域 */
  domain: RouteDomain
  /** 路由路径（与 dashboard 对齐） */
  path: string
  /** 页面名称（用于占位组件显示） */
  pageName: string
}

/** 38 页路由表——按蓝皮书 §一 8 域归属（R2 新增 /appearance；R4-3 砍遥测页；R4-4a 新增 plugin 3 embed） */
export const routeDefinitions: RouteDefinition[] = [
  // config（9 页——R2 新增 /appearance）
  { id: 'config/bot', domain: 'config', path: '/config/bot', pageName: 'BotConfig' },
  { id: 'config/model', domain: 'config', path: '/config/model', pageName: 'ModelConfig' },
  { id: 'config/prompts', domain: 'config', path: '/config/prompts', pageName: 'PromptManagement' },
  { id: 'config/mcp-settings', domain: 'config', path: '/mcp-settings', pageName: 'MCPSettings' },
  { id: 'config/model-presets', domain: 'config', path: '/model-presets', pageName: 'ModelPresets' },
  { id: 'config/prompt-generator', domain: 'config', path: '/config/prompt-generator', pageName: 'PromptGenerator' },
  { id: 'config/pack-market', domain: 'config', path: '/config/pack-market', pageName: 'PackMarket' },
  { id: 'config/pack-detail', domain: 'config', path: '/config/pack-market/$packId', pageName: 'PackDetail' },
  { id: 'config/appearance', domain: 'config', path: '/appearance', pageName: 'Appearance' },

  // chat（2 页）
  { id: 'chat/chat', domain: 'chat', path: '/chat', pageName: 'Chat' },
  { id: 'chat/chat-management', domain: 'chat', path: '/chat-management', pageName: 'ChatManagement' },

  // memory（3 页）
  { id: 'memory/reasoning-process', domain: 'memory', path: '/reasoning-process', pageName: 'ReasoningProcess' },
  { id: 'memory/memory', domain: 'memory', path: '/resource/knowledge-graph', pageName: 'Memory' },
  { id: 'memory/focus', domain: 'memory', path: '/focus', pageName: 'Focus' },

  // resource（4 页）
  { id: 'resource/emoji', domain: 'resource', path: '/resource/emoji', pageName: 'EmojiManagement' },
  { id: 'resource/expression', domain: 'resource', path: '/resource/expression', pageName: 'ExpressionManagement' },
  { id: 'resource/jargon', domain: 'resource', path: '/resource/jargon', pageName: 'JargonManagement' },
  { id: 'resource/knowledge-base', domain: 'resource', path: '/resource/knowledge-base', pageName: 'KnowledgeBase' },

  // monitor（6 页——遥测页已砍）
  { id: 'monitor/deepseek', domain: 'monitor', path: '/deepseek-monitor', pageName: 'DeepSeekMonitor' },
  { id: 'monitor/emotion', domain: 'monitor', path: '/emotion-monitor', pageName: 'EmotionMonitor' },
  { id: 'monitor/relationship', domain: 'monitor', path: '/relationship-monitor', pageName: 'RelationshipMonitor' },
  { id: 'monitor/subagent', domain: 'monitor', path: '/subagent-monitor', pageName: 'SubAgentMonitor' },
  { id: 'monitor/system', domain: 'monitor', path: '/system-monitor', pageName: 'SystemMonitor' },
  { id: 'monitor/logs', domain: 'monitor', path: '/logs', pageName: 'Logs' },

  // agent（2 页）
  { id: 'agent/agent', domain: 'agent', path: '/agents', pageName: 'AgentManagement' },
  { id: 'agent/person', domain: 'agent', path: '/resource/person', pageName: 'PersonManagement' },

  // plugin（4 页 + 3 embed——embed 路由先行注册以支持 marketplace embedded prop 导航）
  { id: 'plugin/plugins', domain: 'plugin', path: '/plugins', pageName: 'Plugins' },
  { id: 'plugin/plugin-config', domain: 'plugin', path: '/plugin-config', pageName: 'PluginConfig' },
  { id: 'plugin/plugin-detail', domain: 'plugin', path: '/plugins/$pluginId', pageName: 'PluginDetail' },
  { id: 'plugin/plugin-mirrors', domain: 'plugin', path: '/plugin-mirrors', pageName: 'PluginMirrors' },
  { id: 'plugin/plugins-embed', domain: 'plugin', path: '/plugins/embed', pageName: 'PluginMarketplaceEmbed' },
  { id: 'plugin/plugin-config-embed', domain: 'plugin', path: '/plugin-config/embed', pageName: 'PluginConfigEmbed' },
  { id: 'plugin/plugin-mirrors-embed', domain: 'plugin', path: '/plugin-mirrors/embed', pageName: 'PluginMirrorsEmbed' },

  // home（4 页——survey 拆为 2 页，setup 砍除）
  { id: 'home/home', domain: 'home', path: '/', pageName: 'Home' },
  { id: 'home/survey-webui-feedback', domain: 'home', path: '/survey/webui-feedback', pageName: 'SurveyWebUIFeedback' },
  { id: 'home/survey-maibot-feedback', domain: 'home', path: '/survey/maibot-feedback', pageName: 'SurveyMaiBotFeedback' },
  { id: 'home/404', domain: 'home', path: '*', pageName: 'NotFound' },
]

/** 路由总数（验收：= 34） */
export const ROUTE_COUNT = routeDefinitions.length

/** 8 功能域列表 */
export const ROUTE_DOMAINS: RouteDomain[] = [
  'config',
  'chat',
  'memory',
  'resource',
  'monitor',
  'agent',
  'plugin',
  'home',
]

/** 按域分组 */
export function getRoutesByDomain(domain: RouteDomain): RouteDefinition[] {
  return routeDefinitions.filter((r) => r.domain === domain)
}