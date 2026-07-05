import { useQuery } from '@tanstack/react-query'
import { Check, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'

import { getChatStreams } from '@/lib/chat-management-api'

interface BindSessionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (sessionId: string) => void
  agentId: string
  boundSessionIds: string[]
}

export function BindSessionDialog({
  open,
  onOpenChange,
  onSelect,
  agentId,
  boundSessionIds,
}: BindSessionDialogProps) {
  const { t } = useTranslation()

  const {
    data: chatStreams = [],
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['chatStreams', agentId],
    queryFn: () => getChatStreams(1000),
    enabled: open,
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('agent.activeSessions.selectSession')}</DialogTitle>
        </DialogHeader>

        <ScrollArea className="max-h-[400px]">
          {isLoading ? (
            <div className="space-y-2 p-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-10 rounded-md bg-muted animate-pulse" />
              ))}
            </div>
          ) : isError ? (
            <div className="flex flex-col items-center gap-2 py-8">
              <span className="text-sm text-muted-foreground">
                {t('agent.activeSessions.loadFailed')}
              </span>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                <RefreshCw className="h-3.5 w-3.5 mr-1" />
                {t('agent.activeSessions.retry')}
              </Button>
            </div>
          ) : chatStreams.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              {t('agent.activeSessions.noAvailableSessions')}
            </div>
          ) : (
            <div className="space-y-1 p-2">
              {chatStreams.map((stream) => {
                const isBound = boundSessionIds.includes(stream.session_id)
                return (
                  <button
                    key={stream.session_id}
                    type="button"
                    disabled={isBound}
                    onClick={() => {
                      onSelect(stream.session_id)
                      onOpenChange(false)
                    }}
                    className="flex items-center justify-between w-full rounded-md px-3 py-2 text-sm hover:bg-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span className="truncate">{stream.display_name}</span>
                    {isBound && (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground shrink-0 ml-2">
                        <Check className="h-3 w-3" />
                        {t('agent.activeSessions.boundStatus')}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}