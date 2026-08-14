/**
 * import-create-card —— Card1「创建导入任务」编排：模式切换（MemoryMiniTabs）+
 * 公共参数（CommonParamsForm）+ 7 个模式表单（TabsContent）+ 提交按钮。
 * 组件本身只做组装，字段声明/渲染细节下沉到 schema 与各 mode-form。
 */
import { Loader2, Upload } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Tabs } from '@/components/ui/tabs'
import { MemoryMiniTabs } from '@/components/memory/MemoryMiniTabs'
import type { MemoryImportTaskKind } from '@/lib/memory-api'

import { IMPORT_KIND_OPTIONS } from '../../constants'
import type { UseImportFormResult } from '../../hooks/useImportForm'
import { CommonParamsForm } from './common-params-form'
import { LpmmConvertForm } from './mode-forms/lpmm-convert-form'
import { LpmmOpenieForm } from './mode-forms/lpmm-openie-form'
import { MaibotMigrationForm } from './mode-forms/maibot-migration-form'
import { PasteForm } from './mode-forms/paste-form'
import { RawScanForm } from './mode-forms/raw-scan-form'
import { TemporalBackfillForm } from './mode-forms/temporal-backfill-form'
import { UploadForm } from './mode-forms/upload-form'

export function ImportCreateCard({ form }: { form: UseImportFormResult }) {
  const { importCreateMode, setImportCreateMode, submitImportByMode, creatingImport } = form
  return (
    <Card className="rounded-2xl border-border/70 shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Upload className="h-4 w-4" />
          创建导入任务
        </CardTitle>
        <CardDescription>按“选择导入方式 → 检查公共参数 → 创建任务”的顺序完成导入。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <Tabs
          value={importCreateMode}
          onValueChange={(value) => setImportCreateMode(value as MemoryImportTaskKind)}
          className="space-y-4"
        >
          <div className="space-y-2">
            <Label>选择导入方式</Label>
            <MemoryMiniTabs items={IMPORT_KIND_OPTIONS} />
          </div>

          <CommonParamsForm form={form} />

          <UploadForm form={form} />
          <PasteForm form={form} />
          <RawScanForm form={form} />
          <LpmmOpenieForm form={form} />
          <LpmmConvertForm form={form} />
          <TemporalBackfillForm form={form} />
          <MaibotMigrationForm form={form} />
        </Tabs>

        <Button onClick={() => void submitImportByMode()} disabled={creatingImport}>
          {creatingImport ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
          创建导入任务
        </Button>
      </CardContent>
    </Card>
  )
}
