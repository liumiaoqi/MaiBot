/**
 * paste 模式表单（schema 消费渲染）——内容名称 + 输入模式 + 粘贴内容。
 */
import { TabsContent } from '@/components/ui/tabs'
import type { MemoryImportInputMode } from '@/lib/memory-api'

import { buildImportFieldMap, IMPORT_MODE_SCHEMAS } from '../../../import-mode-schemas'
import type { UseImportFormResult } from '../../../hooks/useImportForm'
import { SchemaField } from '../schema-field'

export function PasteForm({ form }: { form: UseImportFormResult }) {
  const fields = buildImportFieldMap(IMPORT_MODE_SCHEMAS.paste)
  return (
    <TabsContent value="paste" className="mt-0">
      <div className="space-y-3 rounded-xl border bg-background/70 p-4">
        <div className="text-xs text-muted-foreground">直接粘贴少量文本或 JSON，适合临时补充一段资料。</div>
        <div className="grid gap-3">
          <SchemaField
            field={fields.pasteName}
            value={form.pasteName}
            onChange={(value) => form.setPasteName(String(value))}
          />
          <SchemaField
            field={fields.pasteMode}
            value={form.pasteMode}
            onChange={(value) => form.setPasteMode(value as MemoryImportInputMode)}
          />
          <SchemaField
            field={fields.pasteContent}
            value={form.pasteContent}
            onChange={(value) => form.setPasteContent(String(value))}
          />
        </div>
      </div>
    </TabsContent>
  )
}
