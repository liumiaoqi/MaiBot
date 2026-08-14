/**
 * lpmm_openie 模式表单（schema 消费渲染）——别名/相对路径 + 包含全部 JSON 开关。
 */
import { TabsContent } from '@/components/ui/tabs'

import { buildImportFieldMap, IMPORT_MODE_SCHEMAS } from '../../../import-mode-schemas'
import type { UseImportFormResult } from '../../../hooks/useImportForm'
import { SchemaField } from '../schema-field'

export function LpmmOpenieForm({ form }: { form: UseImportFormResult }) {
  const fields = buildImportFieldMap(IMPORT_MODE_SCHEMAS.lpmm_openie)
  return (
    <TabsContent value="lpmm_openie" className="mt-0">
      <div className="space-y-3 rounded-xl border bg-background/70 p-4">
        <div className="text-xs text-muted-foreground">读取 LPMM 内容并抽取关系</div>
        <div className="grid gap-3">
          <SchemaField
            field={fields.openieAlias}
            value={form.openieAlias}
            onChange={(value) => form.setOpenieAlias(String(value))}
          />
          <SchemaField
            field={fields.openieRelativePath}
            value={form.openieRelativePath}
            onChange={(value) => form.setOpenieRelativePath(String(value))}
          />
        </div>
        <SchemaField
          field={fields.openieIncludeAllJson}
          value={form.openieIncludeAllJson}
          onChange={(value) => form.setOpenieIncludeAllJson(Boolean(value))}
        />
      </div>
    </TabsContent>
  )
}
