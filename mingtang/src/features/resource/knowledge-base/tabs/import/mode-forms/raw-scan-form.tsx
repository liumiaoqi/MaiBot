/**
 * raw_scan 模式表单（schema 消费渲染）——别名/输入模式/相对路径/Glob + 递归开关。
 */
import { TabsContent } from '@/components/ui/tabs'
import type { MemoryImportInputMode } from '@/lib/memory-api'

import { buildImportFieldMap, IMPORT_MODE_SCHEMAS } from '../../../import-mode-schemas'
import type { UseImportFormResult } from '../../../hooks/useImportForm'
import { SchemaField } from '../schema-field'

export function RawScanForm({ form }: { form: UseImportFormResult }) {
  const fields = buildImportFieldMap(IMPORT_MODE_SCHEMAS.raw_scan)
  return (
    <TabsContent value="raw_scan" className="mt-0">
      <div className="space-y-3 rounded-xl border bg-background/70 p-4">
        <div className="text-xs text-muted-foreground">扫描目录文件，适合本地批处理</div>
        <div className="grid gap-3">
          <SchemaField
            field={fields.rawAlias}
            value={form.rawAlias}
            onChange={(value) => form.setRawAlias(String(value))}
          />
          <SchemaField
            field={fields.rawInputMode}
            value={form.rawInputMode}
            onChange={(value) => form.setRawInputMode(value as MemoryImportInputMode)}
          />
          <SchemaField
            field={fields.rawRelativePath}
            value={form.rawRelativePath}
            onChange={(value) => form.setRawRelativePath(String(value))}
          />
          <SchemaField
            field={fields.rawGlob}
            value={form.rawGlob}
            onChange={(value) => form.setRawGlob(String(value))}
          />
        </div>
        <SchemaField
          field={fields.rawRecursive}
          value={form.rawRecursive}
          onChange={(value) => form.setRawRecursive(Boolean(value))}
        />
      </div>
    </TabsContent>
  )
}
