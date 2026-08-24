/**
 * ChatEmbedPage 聊天嵌入页
 *
 * 供外部程序（如 QQ 机器人壳）嵌入使用的纯聊天工作区。
 * 无顶栏无侧边栏——基于 EmbedPageShell 组装，绕过 Layout 挂 rootRoute。
 * auth guard 由 EmbedPageShell 内置（checking 态呈现"麦麦正在啃食服务器..."加载提示）。
 *
 * 数据流：EmbedPageShell（auth guard + TooltipProvider）→ ChatPage（聊天工作区）
 * 约束：不挂载 Layout（路由层挂 rootRoute）；不自造嵌入外壳
 * i18n：页面标题 chat.embed.title
 */
import { useTranslation } from 'react-i18next'

import { EmbedPageShell } from '@/components/embed-page-shell'

import { ChatPage } from './index'

export function ChatEmbedPage(): React.ReactElement {
  const { t } = useTranslation()

  return (
    <EmbedPageShell shellId="embed-chat" title={t('chat.embed.title')}>
      <ChatPage />
    </EmbedPageShell>
  )
}