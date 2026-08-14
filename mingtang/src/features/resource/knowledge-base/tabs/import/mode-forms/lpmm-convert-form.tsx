/**
 * lpmm_convert 模式表单（schema 消费渲染）——源/目标别名与路径 + 维度/批大小。
 */
import { TabsContent } from '@/components/ui/tabs'

import { buildImportFieldMap, IMPORT_MODE_SCHEMAS } from '../../../import-mode-schemas'
import type { UseImportFormResult } from '../../../hooks/useImportForm'
import { SchemaField } from '../schema-field'

export function LpmmConvertForm({ form }: { form: UseImportFormResult }) {
  const fields = buildImportFieldMap(IMPORT_MODE_SCHEMAS.lpmm_convert)
  return (
    <TabsContent value="lpmm_convert" className="mt-0">
      <div className="space-y-3 rounded-xl border bg-background/70 p-4">
        <div className="text-xs text-muted-foreground">将 LPMM 数据转换到目标目录</div>
        <div className="grid gap-3">
          <SchemaField
            field={fields.convertAlias}
            value={form.convertAlias}
            onChange={(value) => form.setConvertAlias(String(value))}
          />
          <SchemaField
            field={fields.convertTargetAlias}
            value={form.convertTargetAlias}
            onChange={(value) => form.setConvertTargetAlias(String(value))}
          />
          <SchemaField
            field={fields.convertRelativePath}
            value={form.convertRelativePath}
            onChange={(value) => form.setConvertRelativePath(String(value))}
          />
          <SchemaField
            field={fields.convertTargetRelativePath}
            value={form.convertTargetRelativePath}
            onChange={(value) => form.setConvertTargetRelativePath(String(value))}
          />
          <SchemaField
            field={fields.convertDimension}
            value={form.convertDimension}
            onChange={(value) => form.setConvertDimension(String(value))}
          />
          <SchemaField
            field={fields.convertBatchSize}
            value={form.convertBatchSize}
            onChange={(value) => form.setConvertBatchSize(String(value))}
          />
        </div>
      </div>
    </TabsContent>
  )
}
