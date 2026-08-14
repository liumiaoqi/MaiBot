/**
 * temporal_backfill 模式表单（schema 消费渲染）——别名/上限/相对路径 + 两个回填开关。
 */
import { TabsContent } from '@/components/ui/tabs'

import { buildImportFieldMap, IMPORT_MODE_SCHEMAS } from '../../../import-mode-schemas'
import type { UseImportFormResult } from '../../../hooks/useImportForm'
import { SchemaField } from '../schema-field'

export function TemporalBackfillForm({ form }: { form: UseImportFormResult }) {
  const fields = buildImportFieldMap(IMPORT_MODE_SCHEMAS.temporal_backfill)
  return (
    <TabsContent value="temporal_backfill" className="mt-0">
      <div className="space-y-3 rounded-xl border bg-background/70 p-4">
        <div className="text-xs text-muted-foreground">为已有数据补齐时间字段</div>
        <div className="grid gap-3">
          <SchemaField
            field={fields.backfillAlias}
            value={form.backfillAlias}
            onChange={(value) => form.setBackfillAlias(String(value))}
          />
          <SchemaField
            field={fields.backfillLimit}
            value={form.backfillLimit}
            onChange={(value) => form.setBackfillLimit(String(value))}
          />
          <SchemaField
            field={fields.backfillRelativePath}
            value={form.backfillRelativePath}
            onChange={(value) => form.setBackfillRelativePath(String(value))}
          />
        </div>
        <div className="grid gap-2">
          <SchemaField
            field={fields.backfillDryRun}
            value={form.backfillDryRun}
            onChange={(value) => form.setBackfillDryRun(Boolean(value))}
          />
          <SchemaField
            field={fields.backfillNoCreatedFallback}
            value={form.backfillNoCreatedFallback}
            onChange={(value) => form.setBackfillNoCreatedFallback(Boolean(value))}
          />
        </div>
      </div>
    </TabsContent>
  )
}
