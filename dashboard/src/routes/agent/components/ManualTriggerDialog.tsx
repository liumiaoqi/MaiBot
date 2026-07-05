import { useTranslation } from 'react-i18next'
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { manualTriggerInteraction, getAgentList } from '@/lib/agent-api'
import { useQuery } from '@tanstack/react-query'
import * as Dialog from '@radix-ui/react-dialog'

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
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[#1a1a2e] border border-white/10 rounded-xl p-6 w-[400px] z-50 space-y-4">
          <Dialog.Title className="text-sm font-medium text-white/80">
            {t('agent.interaction.manualTrigger.title')}
          </Dialog.Title>

          <div className="space-y-3">
            <Field label={t('agent.interaction.manualTrigger.initiator')}>
              <select
                value={initiatorId}
                onChange={(e) => setInitiatorId(e.target.value)}
                className="w-full bg-white/[0.05] border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white/70"
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
                className="w-full bg-white/[0.05] border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white/70"
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
                className="w-full bg-white/[0.05] border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white/70"
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
                className="w-full bg-white/[0.05] border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white/70"
                placeholder={t('agent.interaction.manualTrigger.reason')}
              />
            </Field>
          </div>

          {mutation.isError && (
            <p className="text-xs text-red-400">{t('agent.interaction.manualTrigger.failed')}</p>
          )}

          <div className="flex justify-end gap-2">
            <Dialog.Close className="px-3 py-1.5 text-xs text-white/40 hover:text-white/60">
              {t('common.cancel', '取消')}
            </Dialog.Close>
            <button
              type="button"
              disabled={!initiatorId || !targetId || mutation.isPending}
              onClick={() => mutation.mutate()}
              className="px-4 py-1.5 text-xs bg-indigo-500/20 text-indigo-400 rounded-lg hover:bg-indigo-500/30 disabled:opacity-30"
            >
              {t('agent.interaction.manualTrigger.submit')}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-white/40">{label}</label>
      {children}
    </div>
  )
}