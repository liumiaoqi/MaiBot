import { Activity, Boxes, Database, FileSearch, FileText, Hash, Home, LayoutGrid, MessageSquare, Network, Package, Server, Settings, Sliders, Smile, UserCircle } from 'lucide-react'

import type { MenuSection } from './types'

export const menuSections: MenuSection[] = [
  {
    title: 'sidebar.groups.overview',
    items: [
      { icon: Home, label: 'sidebar.menu.home', path: '/', searchDescription: 'search.items.homeDesc' },
    ],
  },
  {
    title: 'sidebar.groups.botConfig',
    items: [
      { icon: FileText, label: 'sidebar.menu.botMainConfig', path: '/config/bot', searchDescription: 'search.items.botConfigDesc' },
      { icon: Server, label: 'sidebar.menu.aiModelProvider', path: '/config/modelProvider', searchDescription: 'search.items.modelProviderDesc', tourId: 'sidebar-model-provider' },
      { icon: Boxes, label: 'sidebar.menu.modelManagement', path: '/config/model', searchDescription: 'search.items.modelDesc', tourId: 'sidebar-model-management' },
      { icon: Sliders, label: 'sidebar.menu.adapterConfig', path: '/config/adapter' },
    ],
  },
  {
    title: 'sidebar.groups.botResources',
    items: [
      { icon: Smile, label: 'sidebar.menu.emojiManagement', path: '/resource/emoji', searchDescription: 'search.items.emojiDesc' },
      { icon: MessageSquare, label: 'sidebar.menu.expressionManagement', path: '/resource/expression', searchDescription: 'search.items.expressionDesc' },
      { icon: Hash, label: 'sidebar.menu.slangManagement', path: '/resource/jargon', searchDescription: 'search.items.jargonDesc' },
      { icon: UserCircle, label: 'sidebar.menu.personInfo', path: '/resource/person', searchDescription: 'search.items.personDesc' },
      { icon: Network, label: 'sidebar.menu.knowledgeGraph', path: '/resource/knowledge-graph' },
      { icon: Database, label: 'sidebar.menu.knowledgeBase', path: '/resource/knowledge-base' },
    ],
  },
  {
    title: 'sidebar.groups.extensionsMonitor',
    items: [
      { icon: Package, label: 'sidebar.menu.pluginMarket', path: '/plugins', searchDescription: 'search.items.pluginsDesc' },
      { icon: LayoutGrid, label: 'sidebar.menu.configTemplate', path: '/config/pack-market' },
      { icon: Sliders, label: 'sidebar.menu.pluginConfig', path: '/plugin-config' },
      { icon: FileSearch, label: 'sidebar.menu.logViewer', path: '/logs', searchDescription: 'search.items.logsDesc' },
      { icon: Activity, label: 'sidebar.menu.maisakaMonitor', path: '/planner-monitor' },
    ],
  },
  {
    title: 'sidebar.groups.system',
    items: [
      { icon: Settings, label: 'sidebar.menu.settings', path: '/settings', searchDescription: 'search.items.settingsDesc' },
    ],
  },
]
