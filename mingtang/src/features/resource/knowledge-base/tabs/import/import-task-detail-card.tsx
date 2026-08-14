/**
 * import-task-detail-card —— Card4「任务详情」：任务摘要表 + 重试摘要 + 文件状态 + 分块分页表。
 * 数据全部来自 useImportQueue（选中任务/文件/分块 + 取消/重试动作），本组件只负责呈现。
 */
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'

import { MemoryProgressIndicator } from '@/components/memory/MemoryProgressIndicator'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ThinkingIllustration } from '@/components/ui/thinking-illustration'
import { cn } from '@/lib/utils'

import { IMPORT_CHUNK_PAGE_SIZE, RUNNING_IMPORT_STATUS } from '../../constants'
import {
  formatImportTime,
  formatProgressPercent,
  getImportStatusLabel,
  getImportStatusVariant,
  getImportStepLabel,
  normalizeProgress,
} from '../../utils'
import type { UseImportQueueResult } from '../../hooks/useImportQueue'
import { formatChunkSummary } from './utils'

export function ImportTaskDetailCard({ queue }: { queue: UseImportQueueResult }) {
  const {
    selectedImportTaskId,
    cancelSelectedImportTask,
    retrySelectedImportTask,
    selectedImportTaskLoading,
    selectedImportTaskResolved,
    selectedImportRetrySummary,
    selectedImportTaskErrorText,
    selectedImportFiles,
    selectedImportFileId,
    selectImportFile,
    importChunkTotal,
    importChunkOffset,
    moveImportChunkPage,
    canImportChunkPrev,
    canImportChunkNext,
    importChunksLoading,
    selectedImportChunks,
  } = queue
  return (
    <Card className="rounded-2xl border-border/70 bg-card/90 shadow-sm">
      <CardHeader className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>任务详情</CardTitle>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              aria-label="取消选中导入任务"
              onClick={() => void cancelSelectedImportTask()}
              disabled={!selectedImportTaskId}
            >
              取消任务
            </Button>
            <Button
              size="sm"
              aria-label="重试选中导入任务"
              onClick={() => void retrySelectedImportTask()}
              disabled={!selectedImportTaskId}
            >
              重试失败项
            </Button>
          </div>
        </div>
        <CardDescription>支持文件级和分块级状态观察，可直接在当前页面定位失败原因</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {selectedImportTaskLoading ? (
          <div className="flex items-center gap-2">
            <ThinkingIllustration size="sm" />
          </div>
        ) : null}

        {!selectedImportTaskResolved ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed bg-muted/15 px-6 py-10 text-center">
            <div className="rounded-full bg-muted/40 p-3">
              <Loader2 className="h-5 w-5 text-muted-foreground" />
            </div>
            <div className="space-y-1">
              <div className="text-sm font-medium">还没选中任务</div>
              <div className="text-xs leading-relaxed text-muted-foreground">
                在左侧/上方的导入队列里点击任意任务卡片<br />
                即可在这里查看进度、文件状态和分块详情
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              <div className="text-sm font-medium">任务摘要</div>
              <div className="overflow-auto rounded-xl border bg-muted/10">
                <Table className="min-w-[680px]">
                  <TableBody>
                    <TableRow>
                      <TableCell className="w-[140px] text-muted-foreground">任务 ID</TableCell>
                      <TableCell className="break-all font-mono text-xs leading-relaxed">
                        {selectedImportTaskResolved.task_id}
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell className="text-muted-foreground">任务类型</TableCell>
                      <TableCell>
                        {String(selectedImportTaskResolved.task_kind ?? selectedImportTaskResolved.mode ?? '-')}
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell className="text-muted-foreground">状态 / 步骤</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={getImportStatusVariant(String(selectedImportTaskResolved.status ?? ''))}>
                            {getImportStatusLabel(String(selectedImportTaskResolved.status ?? ''))}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {getImportStepLabel(String(selectedImportTaskResolved.current_step ?? ''))}
                          </span>
                        </div>
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell className="text-muted-foreground">进度</TableCell>
                      <TableCell>
                        <MemoryProgressIndicator
                          value={normalizeProgress(selectedImportTaskResolved.progress)}
                          statusLabel={getImportStatusLabel(String(selectedImportTaskResolved.status ?? ''))}
                          stepLabel={getImportStepLabel(String(selectedImportTaskResolved.current_step ?? ''))}
                          tone={
                            String(selectedImportTaskResolved.status ?? '') === 'completed'
                              ? 'success'
                              : String(selectedImportTaskResolved.status ?? '') === 'failed'
                                ? 'destructive'
                                : String(selectedImportTaskResolved.status ?? '') === 'completed_with_errors'
                                  ? 'warning'
                                  : String(selectedImportTaskResolved.status ?? '') === 'cancelled'
                                    ? 'muted'
                                    : 'default'
                          }
                          busy={RUNNING_IMPORT_STATUS.has(String(selectedImportTaskResolved.status ?? ''))}
                          detail={formatChunkSummary(
                            selectedImportTaskResolved.done_chunks,
                            selectedImportTaskResolved.total_chunks,
                            selectedImportTaskResolved.failed_chunks,
                            selectedImportTaskResolved.cancelled_chunks,
                          )}
                        />
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell className="text-muted-foreground">创建时间</TableCell>
                      <TableCell>{formatImportTime(selectedImportTaskResolved.created_at)}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell className="text-muted-foreground">更新时间</TableCell>
                      <TableCell>{formatImportTime(selectedImportTaskResolved.updated_at)}</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
            </div>

            {selectedImportRetrySummary ? (
              <div className="space-y-2">
                <div className="text-sm font-medium">重试摘要</div>
                <div className="overflow-auto rounded-xl border bg-muted/10">
                  <Table>
                    <TableBody>
                      <TableRow>
                        <TableCell className="w-[220px] text-muted-foreground">按分块重试的文件数</TableCell>
                        <TableCell>{Number(selectedImportRetrySummary.chunk_retry_files ?? 0)}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell className="text-muted-foreground">按分块重试的分块数</TableCell>
                        <TableCell>{Number(selectedImportRetrySummary.chunk_retry_chunks ?? 0)}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell className="text-muted-foreground">回退整文件重试数</TableCell>
                        <TableCell>{Number(selectedImportRetrySummary.file_fallback_files ?? 0)}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell className="text-muted-foreground">跳过文件数</TableCell>
                        <TableCell>{Number(selectedImportRetrySummary.skipped_files ?? 0)}</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </div>
              </div>
            ) : null}

            {selectedImportTaskErrorText ? (
              <Alert variant="destructive">
                <AlertDescription>{selectedImportTaskErrorText}</AlertDescription>
              </Alert>
            ) : null}

            <div className="space-y-2.5">
              <div className="text-sm font-medium">文件状态</div>
              {selectedImportFiles.length > 0 ? (
                <ScrollArea className="h-[260px] rounded-xl border bg-muted/10">
                  <div className="space-y-2.5 p-2.5">
                    {selectedImportFiles.map((file) => {
                      const isSelected = file.file_id === selectedImportFileId
                      return (
                        <button
                          key={file.file_id}
                          type="button"
                          onClick={() => void selectImportFile(file.file_id)}
                          className={cn(
                            'w-full rounded-xl border p-4 text-left transition-all',
                            isSelected
                              ? 'border-primary/70 bg-primary/5 shadow-sm'
                              : 'bg-background/80 hover:border-muted-foreground/40 hover:bg-muted/20',
                          )}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="truncate text-sm font-medium">{file.name || file.file_id}</span>
                            <Badge variant={getImportStatusVariant(String(file.status ?? ''))}>
                              {getImportStatusLabel(String(file.status ?? ''))}
                            </Badge>
                          </div>
                          <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                            <span>{getImportStepLabel(String(file.current_step ?? ''))}</span>
                            <span>{formatProgressPercent(file.progress)}</span>
                          </div>
                          <Progress value={normalizeProgress(file.progress)} className="mt-2 h-1.5" />
                          <div className="mt-2 text-xs text-muted-foreground">
                            {formatProgressPercent(file.progress)} · {formatChunkSummary(
                              file.done_chunks,
                              file.total_chunks,
                              file.failed_chunks,
                              file.cancelled_chunks,
                            )}
                          </div>
                          {file.error ? (
                            <div className="mt-2 truncate text-xs text-destructive">{file.error}</div>
                          ) : null}
                        </button>
                      )
                    })}
                  </div>
                </ScrollArea>
              ) : (
                <div className="rounded-xl border bg-muted/20 p-4 text-sm text-muted-foreground">当前任务没有文件明细</div>
              )}
            </div>

            <div className="space-y-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium">分块状态</div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Button
                    size="icon"
                    variant="outline"
                    aria-label="上一页分块"
                    onClick={() => void moveImportChunkPage(-1)}
                    disabled={!canImportChunkPrev}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span>
                    {importChunkTotal > 0
                      ? `${importChunkOffset + 1}-${Math.min(importChunkOffset + IMPORT_CHUNK_PAGE_SIZE, importChunkTotal)}`
                      : '0-0'}
                    {' / '}
                    {importChunkTotal}
                  </span>
                  <Button
                    size="icon"
                    variant="outline"
                    aria-label="下一页分块"
                    onClick={() => void moveImportChunkPage(1)}
                    disabled={!canImportChunkNext}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <div className="overflow-auto rounded-xl border bg-background/80">
                <Table className="min-w-[700px]">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[72px]">序号</TableHead>
                      <TableHead className="w-[108px]">状态</TableHead>
                      <TableHead className="w-[108px]">步骤</TableHead>
                      <TableHead className="w-[84px]">进度</TableHead>
                      <TableHead>错误 / 预览</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {importChunksLoading ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center text-muted-foreground">
                          <ThinkingIllustration size="sm" className="mx-auto" />
                        </TableCell>
                      </TableRow>
                    ) : selectedImportChunks.length > 0 ? (
                      selectedImportChunks.map((chunk) => (
                        <TableRow key={chunk.chunk_id}>
                          <TableCell>{chunk.index}</TableCell>
                          <TableCell>{getImportStatusLabel(String(chunk.status ?? ''))}</TableCell>
                          <TableCell>{getImportStepLabel(String(chunk.step ?? ''))}</TableCell>
                          <TableCell>{formatProgressPercent(chunk.progress)}</TableCell>
                          <TableCell className="max-w-[360px]">
                            <div className="space-y-2">
                              {String(chunk.error ?? '').trim() ? (
                                <div className="rounded-md border border-destructive/30 bg-destructive/5 px-2.5 py-2 text-sm leading-relaxed text-destructive">
                                  {String(chunk.error)}
                                </div>
                              ) : null}
                              <details className="rounded-md border bg-muted/20 px-2.5 py-2 text-xs text-muted-foreground">
                                <summary className="cursor-pointer font-medium text-foreground">
                                  {String(chunk.error ?? '').trim() ? '查看分块预览' : '查看内容详情'}
                                </summary>
                                <div className="mt-2 whitespace-pre-wrap break-words leading-relaxed">
                                  {String(chunk.content_preview ?? '-') || '-'}
                                </div>
                              </details>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center text-muted-foreground">
                          当前页没有分块数据
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
