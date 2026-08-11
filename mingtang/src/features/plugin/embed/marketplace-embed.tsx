import { EmbedPageShell } from '@/components/embed-page-shell'
import { PluginMarketplacePage } from '@/features/plugin/marketplace'

export function PluginMarketplaceEmbedPage() {
  return (
    <EmbedPageShell shellId="embed-plugin-marketplace" title="插件市场">
      <PluginMarketplacePage embedded />
    </EmbedPageShell>
  )
}