/**
 * SessionLearningConfig 学习配置区块（R3-2-3 第⑤区块）
 *
 * 从 dashboard routes/chat-management.tsx 335-402 + 1628-1649 行搬移。
 * 包含：ConfigStatusRow + ConfigStatusRows（表达/黑话两行使用/学习双开关）
 *
 * 适配点：useToast → sonner toast()
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  updateChatStreamLearning,
  type ChatLearningStatus,
  type ChatStreamDetail,
} from '@/lib/chat-management-api'
import { toast } from 'sonner'

import { formatRuleTarget } from '../chat-management-utils'
import { StatusBadge } from './talk-frequency-timeline-rule'
import type { LearningKind } from '../chat-management-utils'

/** 学习配置行（使用/学习双开关 + 命中规则） */
function ConfigStatusRow({
  detail,
  kind,
  title,
  status,
}: {
  detail: ChatStreamDetail
  kind: LearningKind
  title: string
  status: ChatLearningStatus
}) {
  const queryClient = useQueryClient()
  const updateMutation = useMutation({
    mutationFn: (payload: { learn: boolean; use: boolean }) =>
      updateChatStreamLearning(detail.session_id, kind, payload),
    onSuccess: (nextDetail) => {
      queryClient.setQueryData(['chat-stream-detail', detail.session_id], nextDetail)
      void queryClient.invalidateQueries({ queryKey: ['chat-streams'] })
      toast.success(`${title}学习配置已保存`)
    },
    onError: (error) => {
      toast.error(`${title}学习配置保存失败`, {
        description: error instanceof Error ? error.message : '请稍后重试',
      })
    },
  })
  const isSaving = updateMutation.isPending

  const saveStatus = (nextStatus: { learn: boolean; use: boolean }) => {
    updateMutation.mutate(nextStatus)
  }

  return (
    <div className="grid gap-3 rounded-md border p-3 text-sm lg:grid-cols-[5rem_1fr_1fr_minmax(12rem,1.5fr)] lg:items-center">
      <div className="text-base font-medium">{title}</div>
      <div className="flex items-center justify-between gap-3 lg:justify-start">
        <Label className="text-muted-foreground flex items-center gap-2">
          <Checkbox
            checked={status.use}
            disabled={isSaving}
            onCheckedChange={(checked) =>
              saveStatus({ use: checked === true, learn: status.learn })
            }
          />
          使用
        </Label>
        <StatusBadge enabled={status.use} />
      </div>
      <div className="flex items-center justify-between gap-3 lg:justify-start">
        <Label className="text-muted-foreground flex items-center gap-2">
          <Checkbox
            checked={status.learn}
            disabled={isSaving}
            onCheckedChange={(checked) => saveStatus({ use: status.use, learn: checked === true })}
          />
          学习
        </Label>
        <StatusBadge enabled={status.learn} />
      </div>
      <div className="text-muted-foreground min-w-0 text-xs">
        命中规则：<span className="break-all">{formatRuleTarget(status.matched_rule)}</span>
      </div>
    </div>
  )
}

/** 学习配置区块（表达 + 黑话两行） */
function SessionLearningConfig({ detail }: { detail: ChatStreamDetail }) {
  const configRows = [
    { kind: 'expression' as const, title: '表达', status: detail.expression },
    { kind: 'jargon' as const, title: '黑话', status: detail.jargon },
  ]

  return (
    <section className="space-y-2">
      {configRows.map((row) =>
        row.status ? (
          <ConfigStatusRow
            key={row.kind}
            detail={detail}
            kind={row.kind}
            title={row.title}
            status={row.status}
          />
        ) : null
      )}
    </section>
  )
}

export { ConfigStatusRow, SessionLearningConfig }