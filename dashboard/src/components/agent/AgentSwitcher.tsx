import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { getAgentList, type AgentConfigInfo } from '@/lib/agent-api'
import { AgentIndicator } from './AgentIndicator'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'

export interface AgentSwitcherProps {
  currentAgentId: string
  onSelect: (agentId: string) => void
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function AgentSwitcher({
  currentAgentId,
  onSelect,
  open,
  onOpenChange,
}: AgentSwitcherProps) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')

  const { data: agents = [] } = useQuery({
    queryKey: ['agent', 'list'],
    queryFn: getAgentList,
  })

  const filtered = agents.filter(
    (a: AgentConfigInfo) =>
      a.display_name.toLowerCase().includes(search.toLowerCase()) ||
      a.agent_id.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-0 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <Dialog.Title className="text-sm font-semibold">{t('agent.switcher.title')}</Dialog.Title>
            <Dialog.Close className="rounded-sm opacity-70 hover:opacity-100">
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>
          <div className="p-3">
            <input
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground"
              placeholder={t('agent.switcher.searchPlaceholder')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="max-h-72 overflow-y-auto px-2 pb-3">
            {filtered.length === 0 && (
              <div className="py-6 text-center text-sm text-muted-foreground">{t('agent.switcher.noMatch')}</div>
            )}
            {filtered.map((agent: AgentConfigInfo) => (
              <button
                key={agent.agent_id}
                className={cn(
                  'flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm hover:bg-accent transition-colors',
                  agent.agent_id === currentAgentId && 'bg-accent/50',
                )}
                onClick={() => {
                  onSelect(agent.agent_id)
                  onOpenChange(false)
                }}
              >
                <AgentIndicator
                  agent_id={agent.agent_id}
                  display_name={agent.display_name}
                  color={agent.color}
                  size="sm"
                  showName={false}
                />
                <span className="flex-1 text-left font-medium">{agent.display_name}</span>
                {agent.agent_id === currentAgentId && (
                  <span className="text-xs text-muted-foreground">{t('agent.switcher.current')}</span>
                )}
              </button>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}