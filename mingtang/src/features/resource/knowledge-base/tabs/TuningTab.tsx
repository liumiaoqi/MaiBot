/**
 * 调优 Tab（P2-B 结构拆分）——只保留主组件与视图状态；
 * 快照/结果纯函数与常量 → ./tuning/tuning-snapshot.ts；
 * 5 个内联子组件 → ./tuning/ 下的独立文件。
 */
import { useMemo, useState } from 'react'

import { ChevronRight, FileText, ListTree, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { CodeEditor } from '@/components/CodeEditor'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TabsContent } from '@/components/ui/tabs'

import type { UseMemoryTuningResult } from '../hooks/useMemoryTuning'
import {
  buildReadableSnapshotEntries,
  buildSnapshotDiff,
  collectSnapshotEntries,
} from './tuning/tuning-snapshot'
import { SnapshotResultCard } from './tuning/snapshot-result-card'
import { SnapshotSummarySection } from './tuning/snapshot-summary-section'
import { TuningResultOverview } from './tuning/tuning-result-overview'
import { TuningTaskListCard } from './tuning/tuning-task-list-card'

export interface TuningTabProps {
  tuning: UseMemoryTuningResult
}

type SnapshotViewMode = 'summary' | 'toml'

export function TuningTab({ tuning }: TuningTabProps) {
  const { t } = useTranslation()
  const {
    tuningObjective,
    setTuningObjective,
    tuningIntensity,
    setTuningIntensity,
    tuningSampleSize,
    setTuningSampleSize,
    tuningTopKEval,
    setTuningTopKEval,
    persistBestProfile,
    setPersistBestProfile,
    submitTuningTask,
    creatingTuning,
    tuningProfile,
    tuningProfileToml,
    tuningTasks,
    applyBestTask,
  } = tuning
  const [snapshotViewMode, setSnapshotViewMode] = useState<SnapshotViewMode>('summary')
  const runtimeEntries = useMemo(() => collectSnapshotEntries(tuningProfile.runtime), [tuningProfile.runtime])
  const persistableEntries = useMemo(() => collectSnapshotEntries(tuningProfile.persistable), [tuningProfile.persistable])
  const { readableEntries: readableRuntimeEntries, technicalCount: runtimeTechnicalCount } = useMemo(
    () => buildReadableSnapshotEntries(runtimeEntries, t),
    [runtimeEntries, t],
  )
  const { readableEntries: readablePersistableEntries, technicalCount: persistableTechnicalCount } = useMemo(
    () => buildReadableSnapshotEntries(persistableEntries, t),
    [persistableEntries, t],
  )
  const { readableDiffs, technicalDiffCount } = useMemo(
    () => buildSnapshotDiff(runtimeEntries, persistableEntries, t),
    [persistableEntries, runtimeEntries, t],
  )
  const resultTask = useMemo(
    () => tuningTasks.find((task) => String(task.status ?? '') === 'completed') ?? tuningTasks[0],
    [tuningTasks],
  )
  const runtimeResultText = runtimeEntries.length > 0
    ? t('memory.tuning.snapshot.runtimeResultApplied')
    : t('memory.tuning.snapshot.runtimeResultEmpty')
  const persistableResultText = persistableEntries.length > 0
    ? t('memory.tuning.snapshot.persistableResultReady')
    : t('memory.tuning.snapshot.persistableResultEmpty')
  const hasConfigDiff = readableDiffs.length + technicalDiffCount > 0
  const diffResultText = hasConfigDiff
    ? t('memory.tuning.snapshot.diffResultChanged')
    : t('memory.tuning.snapshot.diffResultClean')
  const isSummaryView = snapshotViewMode === 'summary'
  const toggleSnapshotView = () => setSnapshotViewMode(isSummaryView ? 'toml' : 'summary')
  const SnapshotToggleIcon = isSummaryView ? FileText : ListTree

  return (
    <TabsContent value="tuning" className="space-y-4">
      <div className="grid items-start gap-4 xl:grid-cols-[360px_minmax(0,1fr)] 2xl:grid-cols-[400px_minmax(0,1fr)]">
        <div className="space-y-4 xl:sticky xl:top-4 xl:self-start">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-4 w-4" />
                {t('memory.tuning.task.title')}
              </CardTitle>
              <CardDescription>{t('memory.tuning.task.description')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div className="text-sm font-medium">{t('memory.tuning.form.strategy')}</div>
                <div className="grid gap-3">
                  <div className="space-y-2">
                    <Label>{t('memory.tuning.form.objective')}</Label>
                    <Select value={tuningObjective} onValueChange={setTuningObjective}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="precision_priority">{t('memory.tuning.objectives.precision')}</SelectItem>
                        <SelectItem value="balanced">{t('memory.tuning.objectives.balanced')}</SelectItem>
                        <SelectItem value="recall_priority">{t('memory.tuning.objectives.recall')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>{t('memory.tuning.form.intensity')}</Label>
                    <Select value={tuningIntensity} onValueChange={setTuningIntensity}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="quick">{t('memory.tuning.intensity.quick')}</SelectItem>
                        <SelectItem value="standard">{t('memory.tuning.intensity.standard')}</SelectItem>
                        <SelectItem value="deep">{t('memory.tuning.intensity.deep')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
              <div className="space-y-3 border-t pt-4">
                <div className="text-sm font-medium">{t('memory.tuning.form.evalScope')}</div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label>{t('memory.tuning.form.sampleSize')}</Label>
                    <Input type="number" value={tuningSampleSize} onChange={(event) => setTuningSampleSize(event.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label>{t('memory.tuning.form.topKEval')}</Label>
                    <Input type="number" value={tuningTopKEval} onChange={(event) => setTuningTopKEval(event.target.value)} />
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3 border-t pt-4">
                <Checkbox
                  id="persist-best-profile"
                  checked={persistBestProfile}
                  onCheckedChange={(checked) => setPersistBestProfile(checked === true)}
                />
                <Label htmlFor="persist-best-profile">{t('memory.tuning.form.persist')}</Label>
              </div>
              <Button className="w-full" onClick={() => void submitTuningTask()} disabled={creatingTuning}>
                <Sparkles className="mr-2 h-4 w-4" />
                {t('memory.tuning.actions.createTask')}
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="min-w-0 space-y-4">
          <Card className="min-w-0 self-start">
            <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <CardTitle>{t('memory.tuning.snapshot.title')}</CardTitle>
                <CardDescription>
                  {isSummaryView ? t('memory.tuning.snapshot.summaryDescription') : t('memory.tuning.snapshot.tomlDescription')}
                </CardDescription>
              </div>
              {!isSummaryView ? (
                <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={toggleSnapshotView}>
                  <SnapshotToggleIcon className="h-4 w-4" />
                  {t('memory.tuning.actions.showSummary')}
                </Button>
              ) : null}
            </CardHeader>
            <CardContent className="space-y-4">
              {snapshotViewMode === 'summary' ? (
                <>
                  <TuningResultOverview task={resultTask} t={t} />

                  <details className="group overflow-hidden rounded-md border bg-background">
                    <summary className="flex cursor-pointer list-none flex-col gap-1 px-4 py-3 text-sm font-medium outline-none transition-colors hover:bg-muted/30 focus-visible:ring-2 focus-visible:ring-ring sm:flex-row sm:items-center [&::-webkit-details-marker]:hidden">
                      <span className="flex min-w-0 items-center gap-2">
                        <ChevronRight className="h-4 w-4 shrink-0 transition-transform group-open:rotate-90" />
                        <span>{t('memory.tuning.snapshot.detailsTitle')}</span>
                      </span>
                      <span className="text-xs font-normal text-muted-foreground sm:ml-auto">
                        {t('memory.tuning.snapshot.detailsHint')}
                      </span>
                    </summary>
                    <div className="border-t">
                      <section className="grid gap-3 p-4 md:grid-cols-3">
                        <SnapshotResultCard
                          title={t('memory.tuning.snapshot.runtimeTitle')}
                          description={runtimeResultText}
                        />
                        <SnapshotResultCard
                          title={t('memory.tuning.snapshot.persistableTitle')}
                          description={persistableResultText}
                        />
                        <SnapshotResultCard
                          title={t('memory.tuning.snapshot.diffTitle')}
                          description={diffResultText}
                        />
                      </section>
                      <div className="flex items-center justify-between gap-3 border-t px-4 py-3">
                        <div className="text-sm font-medium">{t('memory.tuning.snapshot.parameterDetailsTitle')}</div>
                        <Button type="button" variant="ghost" size="sm" onClick={toggleSnapshotView}>
                          <FileText className="h-4 w-4" />
                          {t('memory.tuning.actions.showToml')}
                        </Button>
                      </div>
                      <div className="max-h-[30vh] overflow-y-auto overscroll-contain border-t px-4 py-4 pr-3">
                        <div className="space-y-4">
                          <SnapshotSummarySection
                            title={t('memory.tuning.snapshot.runtimeTitle')}
                            description={t('memory.tuning.snapshot.runtimeDescription')}
                            entries={readableRuntimeEntries}
                            technicalCount={runtimeTechnicalCount}
                            technicalNote={t('memory.tuning.snapshot.technicalCount', { count: runtimeTechnicalCount })}
                            emptyText={t('memory.tuning.snapshot.empty')}
                          />
                          <SnapshotSummarySection
                            title={t('memory.tuning.snapshot.persistableTitle')}
                            description={t('memory.tuning.snapshot.persistableDescription')}
                            entries={readablePersistableEntries}
                            technicalCount={persistableTechnicalCount}
                            technicalNote={t('memory.tuning.snapshot.technicalCount', { count: persistableTechnicalCount })}
                            emptyText={t('memory.tuning.snapshot.empty')}
                          />
                          <section className="space-y-3 rounded-md border bg-background p-4">
                            <div>
                              <div className="text-sm font-medium">{t('memory.tuning.snapshot.diffTitle')}</div>
                              <div className="text-xs text-muted-foreground">{t('memory.tuning.snapshot.diffDescription')}</div>
                            </div>
                            {readableDiffs.length > 0 ? (
                              <div className="space-y-2">
                                {readableDiffs.map((entry) => (
                                  <div key={entry.path} className="grid gap-2 rounded-md border bg-background p-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                                    <div className="text-xs leading-5 text-muted-foreground lg:col-span-2">{entry.label}</div>
                                    <div className="min-w-0">
                                      <div className="text-[11px] text-muted-foreground">{t('memory.tuning.snapshot.runtimeShort')}</div>
                                      <div className="break-all text-sm leading-6">{entry.runtime}</div>
                                    </div>
                                    <div className="min-w-0">
                                      <div className="text-[11px] text-muted-foreground">{t('memory.tuning.snapshot.persistableShort')}</div>
                                      <div className="break-all text-sm leading-6">{entry.persistable}</div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                                {t('memory.tuning.snapshot.noDiff')}
                              </div>
                            )}
                            {technicalDiffCount > 0 ? (
                              <div className="rounded-md border border-dashed bg-background/60 p-3 text-xs text-muted-foreground">
                                {t('memory.tuning.snapshot.technicalDiffCount', { count: technicalDiffCount })}
                              </div>
                            ) : null}
                          </section>
                        </div>
                      </div>
                    </div>
                  </details>
                </>
              ) : (
                <CodeEditor
                  value={tuningProfileToml}
                  language="toml"
                  readOnly
                  height="640px"
                />
              )}
            </CardContent>
          </Card>

          <TuningTaskListCard tasks={tuningTasks} applyBestTask={applyBestTask} t={t} />
        </div>
      </div>
    </TabsContent>
  )
}
