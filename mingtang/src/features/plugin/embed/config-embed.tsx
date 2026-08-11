import { EmbedPageShell } from '@/components/embed-page-shell'
import { PluginConfigPage } from '@/features/plugin/config'

export function PluginConfigEmbedPage() {
  return (
    <EmbedPageShell shellId="embed-plugin-config" title="插件管理">
      <PluginConfigPage />
    </EmbedPageShell>
  )
}