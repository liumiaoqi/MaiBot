import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { KeyValueEditor } from './key-value-editor'

export interface ExtraParamsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  value: Record<string, unknown>
  onChange: (value: Record<string, unknown>) => void
}

/** 额外参数对话框——JSON 编辑 + 校验 */
export function ExtraParamsDialog({
  open,
  onOpenChange,
  value,
  onChange,
}: ExtraParamsDialogProps) {
  const [editingValue, setEditingValue] = useState<Record<string, unknown>>(value)

  // 打开/值变化时同步编辑内容——渲染期调整模式（React 官方——替代 effect 里 setState）
  const [prevSyncProps, setPrevSyncProps] = useState({ open, value })
  if (open && (prevSyncProps.open !== open || prevSyncProps.value !== value)) {
    setPrevSyncProps({ open, value })
    setEditingValue(value)
  }

  const handleOpenChange = (newOpen: boolean) => {
    if (newOpen) {
      setEditingValue(value)
    }
    onOpenChange(newOpen)
  }

  const handleSave = () => {
    onChange(editingValue)
    onOpenChange(false)
  }

  const handleCancel = () => {
    setEditingValue(value)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>编辑额外参数</DialogTitle>
          <DialogDescription>
            配置模型调用时的额外参数，支持嵌套对象和数组
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-[300px]">
          <KeyValueEditor
            value={editingValue}
            onChange={setEditingValue}
            placeholder="添加额外参数（如 thinking、top_p 等）..."
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleCancel}>
            取消
          </Button>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}