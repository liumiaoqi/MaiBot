import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation } from '@tanstack/react-query'
import { PageShell } from '@/components/biz/page-shell'
import { LoadingSkeleton } from '@/components/biz/loading-skeleton'
import { Button } from '@/components/ui/button'
import { useParams } from '@tanstack/react-router'
import { Heart, Download, Check } from 'lucide-react'
import { getPack, detectPackConflicts, applyPack, recordPackDownload, type ModelPack } from '@/lib/pack-api'

type WizardStep = 1 | 2 | 3

/** 配置模板详情页（/config/pack-market/$packId）——3 步向导 + 冲突检测 */
export function PackDetailPage() {
  const { t } = useTranslation()
  const { packId } = useParams({ strict: false }) as { packId: string }

  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardStep, setWizardStep] = useState<WizardStep>(1)
  const [selectedProviders, setSelectedProviders] = useState<Set<string>>(new Set())
  const [taskMode, setTaskMode] = useState<'append' | 'replace'>('append')

  const { data: pack, isLoading } = useQuery({
    queryKey: ['api', 'pack', packId],
    queryFn: () => getPack(packId),
  })

  const conflictsMutation = useMutation({
    mutationFn: () => {
      if (!packData) throw new Error('Pack data not loaded')
      return detectPackConflicts(packData)
    },
  })

  const applyMutation = useMutation({
    mutationFn: () => {
      if (!packData) throw new Error('Pack data not loaded')
      return applyPack(packData, {
        apply_providers: selectedProviders.size > 0,
        apply_models: true,
        apply_task_config: true,
        task_mode: taskMode,
        selected_providers: Array.from(selectedProviders),
      }, {}, {})
    },
    onSuccess: () => recordPackDownload(packId),
  })

  const packData = pack as ModelPack | undefined

  const handleStartWizard = () => {
    setWizardOpen(true)
    setWizardStep(1)
    conflictsMutation.mutate()
  }

  return (
    <PageShell
      title={`配置模板 ${packId}`}
      breadcrumb={[t('sidebar.groups.botConfig'), t('sidebar.menu.configTemplate'), packId]}
    >
      {isLoading ? <LoadingSkeleton /> : (
        <div className="space-y-4">
          {/* 头部信息 + 操作 */}
          <div className="flex items-center justify-between" data-testid="pack-detail-header">
            <div>
              <h2 className="text-xl font-bold">{packData?.name ?? packId}</h2>
              <p className="text-sm text-muted-foreground">{packData?.description}</p>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={handleStartWizard} data-testid="pack-apply">
                <Download className="h-4 w-4 mr-1" />
                应用模板
              </Button>
              <Button size="sm" variant="outline" data-testid="pack-like">
                <Heart className="h-4 w-4 mr-1" />
                点赞
              </Button>
            </div>
          </div>

          {/* 统计卡片 */}
          <div className="grid grid-cols-3 gap-4" data-testid="pack-detail-stats">
            <div className="rounded-md border p-3 text-center">
              <div className="text-2xl font-bold">{packData?.providers?.length ?? 0}</div>
              <div className="text-xs text-muted-foreground">厂商</div>
            </div>
            <div className="rounded-md border p-3 text-center">
              <div className="text-2xl font-bold">{packData?.models?.length ?? 0}</div>
              <div className="text-xs text-muted-foreground">模型</div>
            </div>
            <div className="rounded-md border p-3 text-center">
              <div className="text-2xl font-bold">{packData?.task_config ? Object.keys(packData.task_config).length : 0}</div>
              <div className="text-xs text-muted-foreground">任务</div>
            </div>
          </div>

          {/* 应用向导 */}
          {wizardOpen && (
            <div className="rounded-md border p-4 space-y-4" data-testid="pack-wizard">
              <h3 className="font-semibold">应用向导（步骤 {wizardStep}/3）</h3>

              {wizardStep === 1 && (
                <div className="space-y-2" data-testid="pack-wizard-step1">
                  <p className="text-sm">选择要应用的内容：</p>
                  <div className="space-y-1">
                    {(packData?.providers ?? []).map((p) => (
                      <label key={p.name} className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={selectedProviders.has(p.name)} onChange={() => {
                          const next = new Set(selectedProviders)
                          next.has(p.name) ? next.delete(p.name) : next.add(p.name)
                          setSelectedProviders(next)
                        }} />
                        {p.name}
                      </label>
                    ))}
                  </div>
                  <div>
                    <label className="text-sm">任务应用模式</label>
                    <select value={taskMode} onChange={(e) => setTaskMode(e.target.value as 'append' | 'replace')} className="ml-2 px-2 py-1 text-sm rounded border">
                      <option value="append">追加合并去重</option>
                      <option value="replace">替换覆盖</option>
                    </select>
                  </div>
                  <Button size="sm" onClick={() => setWizardStep(2)}>下一步</Button>
                </div>
              )}

              {wizardStep === 2 && (
                <div className="space-y-2" data-testid="pack-wizard-step2">
                  <p className="text-sm">提供商映射：</p>
                  {conflictsMutation.data && (
                    <p className="text-xs text-amber-600">检测到冲突，请确认映射</p>
                  )}
                  <Button size="sm" onClick={() => setWizardStep(3)}>下一步</Button>
                  <Button size="sm" variant="outline" onClick={() => setWizardStep(1)}>上一步</Button>
                </div>
              )}

              {wizardStep === 3 && (
                <div className="space-y-2" data-testid="pack-wizard-step3">
                  <p className="text-sm">确认应用：</p>
                  <div className="text-xs text-muted-foreground space-y-1">
                    <p>厂商：{Array.from(selectedProviders).join(', ')}</p>
                    <p>任务模式：{taskMode === 'append' ? '追加合并去重' : '替换覆盖'}</p>
                  </div>
                  <Button size="sm" onClick={() => applyMutation.mutate()} disabled={applyMutation.isPending} data-testid="pack-wizard-confirm">
                    {applyMutation.isSuccess ? <><Check className="h-4 w-4 mr-1" />已应用</> : '确认应用'}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setWizardStep(2)}>上一步</Button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </PageShell>
  )
}
