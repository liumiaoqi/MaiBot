/**
 * MirrorFormDialog —— 镜像源添加/编辑共用表单对话框（R4 债清理 P2）。
 *
 * 收编 mirrors/index.tsx 中 add/edit 两个 Dialog 的 ~100 行重复实现，
 * 以 mode: 'add' | 'edit' 参数化：标题/描述/提交按钮文案、ID 字段可编辑性、
 * 表单控件 id 统一（mirror-*）。表单状态仍由页面持有（formData 单一来源），
 * 本组件只做展示与 onChange 透传。
 */
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

export interface MirrorFormData {
  id: string
  name: string
  raw_prefix: string
  clone_prefix: string
  enabled: boolean
  priority: number
}

interface MirrorFormDialogProps {
  /** add：可填 ID；edit：ID 只读 */
  mode: 'add' | 'edit'
  open: boolean
  onOpenChange: (open: boolean) => void
  formData: MirrorFormData
  onFormDataChange: (next: MirrorFormData) => void
  onSubmit: () => void
}

export function MirrorFormDialog({
  mode,
  open,
  onOpenChange,
  formData,
  onFormDataChange,
  onSubmit,
}: MirrorFormDialogProps) {
  const isAdd = mode === 'add'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isAdd ? '添加镜像源' : '编辑镜像源'}</DialogTitle>
          <DialogDescription>
            {isAdd ? '添加新的 Git 镜像源配置' : '修改镜像源配置'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="mirror-id">
              {isAdd ? '镜像源 ID *' : '镜像源 ID'}
            </Label>
            <Input
              id="mirror-id"
              placeholder={isAdd ? '例如: my-mirror' : undefined}
              value={formData.id}
              disabled={!isAdd}
              onChange={(e) => onFormDataChange({ ...formData, id: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mirror-name">名称 *</Label>
            <Input
              id="mirror-name"
              placeholder="例如: 我的镜像源"
              value={formData.name}
              onChange={(e) => onFormDataChange({ ...formData, name: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mirror-raw">Raw 文件前缀 *</Label>
            <Input
              id="mirror-raw"
              placeholder="https://example.com/raw"
              value={formData.raw_prefix}
              onChange={(e) => onFormDataChange({ ...formData, raw_prefix: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mirror-clone">克隆前缀 *</Label>
            <Input
              id="mirror-clone"
              placeholder="https://example.com/clone"
              value={formData.clone_prefix}
              onChange={(e) => onFormDataChange({ ...formData, clone_prefix: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mirror-priority">优先级</Label>
            <Input
              id="mirror-priority"
              type="number"
              min="1"
              value={formData.priority}
              onChange={(e) =>
                onFormDataChange({ ...formData, priority: Number.parseInt(e.target.value, 10) || 1 })}
            />
            <p className="text-xs text-muted-foreground">数字越小优先级越高</p>
          </div>
          <div className="flex items-center space-x-2">
            <Switch
              id="mirror-enabled"
              checked={formData.enabled}
              onCheckedChange={(checked) => onFormDataChange({ ...formData, enabled: checked })}
            />
            <Label htmlFor="mirror-enabled">启用此镜像源</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={onSubmit}>
            {isAdd ? '添加' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
