import { useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { PageShell } from '@/components/biz/page-shell'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'

import {
  submitRelationFeedback,
  type RelationFeedbackDecision,
  type RelationFeedbackResult,
} from './relation-feedback'

/** decision 显式三选（与后端 `raise / lower / neutral` 一一对应） */
const DECISION_OPTIONS: RelationFeedbackDecision[] = ['raise', 'lower', 'neutral']

/**
 * 关系真值回路页（0004）：人给一个显式判断 ⇒ 改关系强度 + 写账本。
 *
 * 刻意只做「人按按钮」这一种驱动形态——系统不做自动推断；
 * 因此表单**没有默认判断**，未选 `decision` 就不发请求。
 */
export function MemoryRelationsPage() {
  const { t } = useTranslation()
  const [target, setTarget] = useState('')
  const [decision, setDecision] = useState<RelationFeedbackDecision | ''>('')
  const [reason, setReason] = useState('')
  const [updatedBy, setUpdatedBy] = useState('webui')
  const [submitting, setSubmitting] = useState(false)
  const [lastResult, setLastResult] = useState<RelationFeedbackResult | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const trimmedTarget = target.trim()
    if (!trimmedTarget) {
      toast.error(t('memoryRelations.errors.targetRequired'))
      return
    }
    if (!decision) {
      toast.error(t('memoryRelations.errors.decisionRequired'))
      return
    }

    setSubmitting(true)
    try {
      const result = await submitRelationFeedback({
        target: trimmedTarget,
        decision,
        reason: reason.trim(),
        updated_by: updatedBy.trim() || 'webui',
      })
      setLastResult(result)
      if (!result.success) {
        toast.error(result.error || t('memoryRelations.errors.submitFailed'))
        return
      }
      toast.success(t('memoryRelations.result.success'))
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      toast.error(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PageShell
      title={t('memoryRelations.title')}
      breadcrumb={[t('memoryRelations.domain'), t('memoryRelations.title')]}
    >
      <div className="mx-auto max-w-2xl space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{t('memoryRelations.form.title')}</CardTitle>
            <CardDescription>{t('memoryRelations.description')}</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <Label htmlFor="relation-feedback-target">{t('memoryRelations.form.target')}</Label>
                <Input
                  id="relation-feedback-target"
                  value={target}
                  onChange={(event) => setTarget(event.target.value)}
                  placeholder={t('memoryRelations.form.targetPlaceholder')}
                  autoComplete="off"
                />
              </div>

              <div className="space-y-2">
                <Label>{t('memoryRelations.form.decision')}</Label>
                <RadioGroup
                  value={decision}
                  onValueChange={(value) => setDecision(value as RelationFeedbackDecision)}
                  aria-label={t('memoryRelations.form.decision')}
                >
                  {DECISION_OPTIONS.map((option) => (
                    <div key={option} className="flex items-center gap-2">
                      <RadioGroupItem
                        value={option}
                        id={`relation-feedback-decision-${option}`}
                        aria-label={t(`memoryRelations.form.decisions.${option}`)}
                      />
                      <Label htmlFor={`relation-feedback-decision-${option}`}>
                        {t(`memoryRelations.form.decisions.${option}`)}
                      </Label>
                    </div>
                  ))}
                </RadioGroup>
              </div>

              <div className="space-y-2">
                <Label htmlFor="relation-feedback-reason">{t('memoryRelations.form.reason')}</Label>
                <Textarea
                  id="relation-feedback-reason"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder={t('memoryRelations.form.reasonPlaceholder')}
                  autoResize
                  minHeight={72}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="relation-feedback-updated-by">
                  {t('memoryRelations.form.updatedBy')}
                </Label>
                <Input
                  id="relation-feedback-updated-by"
                  value={updatedBy}
                  onChange={(event) => setUpdatedBy(event.target.value)}
                  autoComplete="off"
                />
              </div>

              <Button type="submit" disabled={submitting}>
                {submitting
                  ? t('memoryRelations.form.submitting')
                  : t('memoryRelations.form.submit')}
              </Button>
            </form>
          </CardContent>
        </Card>

        {lastResult?.success && (
          <Card>
            <CardHeader>
              <CardTitle>{t('memoryRelations.result.title')}</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-2 text-sm">
                <dt className="text-muted-foreground">{t('memoryRelations.result.action')}</dt>
                <dd>
                  {lastResult.action
                    ? t(`memoryRelations.form.decisions.${lastResult.action}`)
                    : '—'}
                </dd>
                <dt className="text-muted-foreground">{t('memoryRelations.result.delta')}</dt>
                <dd>{lastResult.delta ?? 0}</dd>
                <dt className="text-muted-foreground">
                  {t('memoryRelations.result.confidenceAfter')}
                </dt>
                <dd>{lastResult.confidence_after ?? '—'}</dd>
                <dt className="text-muted-foreground">{t('memoryRelations.result.eventId')}</dt>
                <dd>{lastResult.event_id ?? '—'}</dd>
              </dl>
              {lastResult.action === 'neutral' && (
                <p className="mt-3 text-sm text-muted-foreground">
                  {t('memoryRelations.result.neutralHint')}
                </p>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </PageShell>
  )
}
