/** 菜单分区数据（从 dashboard/src/components/layout/constants.ts 搬移——去掉 React 图标组件，保留数据） */

export interface MenuItemData {
  /** i18n key for label */
  label: string
  /** 路由路径 */
  path?: string
  /** i18n key for searchDescription */
  searchDescription?: string
  /** 图标名称（Layout 组件按名称渲染） */
  icon: string
  /** 引导 ID */
  tourId?: string
}

export interface MenuSectionData {
  /** i18n key for section title */
  title: string
  items: MenuItemData[]
}

/** 菜单分区——searchDescription 全部补全（R1-3-8） */
export const menuSections: MenuSectionData[] = [
  {
    title: 'sidebar.groups.overview',
    items: [
      { icon: 'home', label: 'sidebar.menu.home', path: '/', searchDescription: 'search.items.homeDesc' },
      { icon: 'agent', label: 'sidebar.menu.agentManagement', path: '/agents', searchDescription: 'search.items.agentManagementDesc' },
      { icon: 'emotion', label: 'sidebar.menu.emotionMonitor', path: '/emotion-monitor', searchDescription: 'search.items.emotionMonitorDesc' },
      { icon: 'relationship', label: 'sidebar.menu.relationshipMonitor', path: '/relationship-monitor', searchDescription: 'search.items.relationshipMonitorDesc' },
      { icon: 'subagent', label: 'sidebar.menu.subagentMonitor', path: '/subagent-monitor', searchDescription: 'search.items.subagentMonitorDesc' },
      { icon: 'deepseek', label: 'sidebar.menu.deepseekMonitor', path: '/deepseek-monitor', searchDescription: 'search.items.deepseekMonitorDesc' },

      { icon: 'system', label: 'sidebar.menu.systemMonitor', path: '/system-monitor', searchDescription: 'search.items.systemMonitorDesc' },
      { icon: 'chat-management', label: 'sidebar.menu.chatManagement', path: '/chat-management', searchDescription: 'search.items.chatManagementDesc' },
    ],
  },
  {
    title: 'sidebar.groups.botConfig',
    items: [
      { icon: 'bot-config', label: 'sidebar.menu.botMainConfig', path: '/config/bot', searchDescription: 'search.items.botConfigDesc' },
      { icon: 'model', label: 'sidebar.menu.modelManagement', path: '/config/model', searchDescription: 'search.items.modelDesc', tourId: 'sidebar-model-management' },
      { icon: 'prompt', label: 'sidebar.menu.promptManagement', path: '/config/prompts', searchDescription: 'search.items.promptManagementDesc' },
      { icon: 'palette', label: 'sidebar.menu.appearance', path: '/appearance', searchDescription: 'search.items.appearanceDesc' },
    ],
  },
  {
    title: 'sidebar.groups.botResources',
    items: [
      { icon: 'emoji', label: 'sidebar.menu.emojiManagement', path: '/resource/emoji', searchDescription: 'search.items.emojiDesc' },
      { icon: 'expression', label: 'sidebar.menu.expressionManagement', path: '/resource/expression', searchDescription: 'search.items.expressionDesc' },
      { icon: 'jargon', label: 'sidebar.menu.slangManagement', path: '/resource/jargon', searchDescription: 'search.items.jargonDesc' },
      { icon: 'behavior', label: 'sidebar.menu.behavior' },
      { icon: 'knowledge', label: 'sidebar.menu.knowledgeBase', path: '/resource/knowledge-base', searchDescription: 'search.items.knowledgeBaseDesc' },
    ],
  },
  {
    title: 'sidebar.groups.extensionsMonitor',
    items: [
      { icon: 'plugin-config', label: 'sidebar.menu.pluginConfig', path: '/plugin-config', searchDescription: 'search.items.pluginConfigDesc' },
      { icon: 'plugin-market', label: 'sidebar.menu.pluginMarket', path: '/plugins', searchDescription: 'search.items.pluginsDesc' },
      { icon: 'mcp', label: 'sidebar.menu.mcpSettings', path: '/mcp-settings', searchDescription: 'search.items.mcpSettingsDesc' },
    ],
  },
]

/** 所有有 path 的菜单项（用于手动登记） */
export const menuItemsWithPath = menuSections
  .flatMap((s) => s.items)
  .filter((item): item is MenuItemData & { path: string } => Boolean(item.path))
