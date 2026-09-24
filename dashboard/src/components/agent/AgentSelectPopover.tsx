import { useState } from 'react'
import * as Popover from '@radix-ui/react-popover'
import { getAgentList, type AgentConfigInfo } from '@/lib/agent-api'
import { AgentIndicator } from './AgentIndicator'
import { cn } from '@/lib/utils'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

export interface AgentSelectPopoverProps {
  currentAgentId: string
  onSelect: (agentId: string) => void
  children: React.ReactNode
  className?: string
}

export function AgentSelectPopover({
  currentAgentId,
  onSelect,
  children,
  className,
}: AgentSelectPopoverProps) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)

  const { data: agents = [] } = useQuery({
    queryKey: ['agent', 'list'],
    queryFn: getAgentList,
    enabled: open,
  })

  const filtered = agents.filter(
    (a: AgentConfigInfo) =>
      a.display_name.toLowerCase().includes(search.toLowerCase()) ||
      a.agent_id.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>{children}</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className={cn(
            'z-50 w-64 rounded-md border bg-popover p-2 shadow-md',
            'data-[state=open]:animate-in data-[state=closed]:animate-out',
            'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
            'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
            className,
          )}
          side="bottom"
          align="start"
          sideOffset={4}
        >
          <input
            className="w-full rounded-sm border bg-background px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground mb-1"
            placeholder={t('agent.selectPopover.searchPlaceholder')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="max-h-60 overflow-y-auto">
            {filtered.length === 0 && (
              <div className="px-2 py-4 text-center text-sm text-muted-foreground">{t('agent.selectPopover.noMatch')}</div>
            )}
            {filtered.map((agent: AgentConfigInfo) => (
              <button
                key={agent.agent_id}
                className={cn(
                  'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent transition-colors',
                  agent.agent_id === currentAgentId && 'bg-accent/50',
                )}
                onClick={() => {
                  onSelect(agent.agent_id)
                  setOpen(false)
                }}
              >
                <AgentIndicator
                  agent_id={agent.agent_id}
                  display_name={agent.display_name}
                  color={agent.color}
                  size="sm"
                  showName={false}
                />
                <span className="flex-1 text-left">{agent.display_name}</span>
                {agent.agent_id === currentAgentId && (
                  <span className="text-xs text-muted-foreground">✓</span>
                )}
              </button>
            ))}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}