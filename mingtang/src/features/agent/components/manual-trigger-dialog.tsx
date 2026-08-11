import { useTranslation } from 'react-i18next'
import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Dialog, DialogClose, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { manualTriggerInteraction, getAgentList } from '@/lib/agent-api'

const INTERACTION_TYPES = [
  'emotion_driven',
  'time_awareness',
  'mention_propagation',
  'event_ripple',
  'inner_need',
  'memory_driven',
]

interface ManualTriggerDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ManualTriggerDialog({ open, onOpenChange }: ManualTriggerDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const [initiatorId, setInitiatorId] = useState('')
  const [targetId, setTargetId] = useState('')
  const [interactionType, setInteractionType] = useState('emotion_driven')
  const [reason, setReason] = useState('')

  const { data: agents = [] } = useQuery({
    queryKey: ['agent', 'list'],
    queryFn: getAgentList,
  })

  const mutation = useMutation({
    mutationFn: () =>
      manualTriggerInteraction({
        initiator_id: initiatorId,
        target_id: targetId,
        interaction_type: interactionType,
        reason,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent', 'interactions'] })
      onOpenChange(false)
      setInitiatorId('')
      setTargetId('')
      setReason('')
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md space-y-4">
        <DialogTitle className="text-sm font-medium">
          {t('agent.interaction.manualTrigger.title')}
        </DialogTitle>

        <div className="space-y-3">
          <Field label={t('agent.interaction.manualTrigger.initiator')}>
            <select
              value={initiatorId}
              onChange={(e) => setInitiatorId(e.target.value)}
              className="w-full bg-muted/30 border border-border rounded-lg px-3 py-1.5 text-sm text-foreground"
            >
              <option value="">--</option>
              {agents.map((a) => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.display_name || a.agent_id}
                </option>
              ))}
            </select>
          </Field>

          <Field label={t('agent.interaction.manualTrigger.target')}>
            <select
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              className="w-full bg-muted/30 border border-border rounded-lg px-3 py-1.5 text-sm text-foreground"
            >
              <option value="">--</option>
              {agents.map((a) => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.display_name || a.agent_id}
                </option>
              ))}
            </select>
          </Field>

          <Field label={t('agent.interaction.manualTrigger.type')}>
            <select
              value={interactionType}
              onChange={(e) => setInteractionType(e.target.value)}
              className="w-full bg-muted/30 border border-border rounded-lg px-3 py-1.5 text-sm text-foreground"
            >
              {INTERACTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {t(`agent.interaction.typeLabels.${type}`, type)}
                </option>
              ))}
            </select>
          </Field>

          <Field label={t('agent.interaction.manualTrigger.reason')}>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full bg-muted/30 border border-border rounded-lg px-3 py-1.5 text-sm text-foreground"
              placeholder={t('agent.interaction.manualTrigger.reason')}
            />
          </Field>
        </div>

        {mutation.isError && (
          <p className="text-xs text-destructive">{t('agent.interaction.manualTrigger.failed')}</p>
        )}

        <div className="flex justify-end gap-2">
          <DialogClose className="px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground">
            {t('common.cancel', '取消')}
          </DialogClose>
          <button
            type="button"
            disabled={!initiatorId || !targetId || mutation.isPending}
            onClick={() => mutation.mutate()}
            className="px-4 py-1.5 text-xs bg-primary/20 text-primary rounded-lg hover:bg-primary/30 disabled:opacity-30"
          >
            {t('agent.interaction.manualTrigger.submit')}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-muted-foreground">{label}</label>
      {children}
    </div>
  )
}