/**
 * PluginStats —— 插件统计占位组件。
 *
 * mingtang 未引入完整插件市场统计 UI，这里以占位文案呈现，
 * 维持调用方 props 契约（pluginId + 可选 className）不变。
 */
interface PluginStatsProps {
  pluginId: string
  className?: string
}

export function PluginStats({ pluginId, className }: PluginStatsProps) {
  return <div className={className}>插件统计（{pluginId}）</div>
}