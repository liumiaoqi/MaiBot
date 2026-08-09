import { AlertCircle } from 'lucide-react'

export function LlmErrorDetails({ error }: { error: string }) {
  return (
    <div className="border-destructive/30 bg-destructive/10 flex min-h-[120px] flex-col items-center justify-center gap-3 rounded-md border p-4 text-center">
      <AlertCircle className="text-destructive h-8 w-8" />
      <div className="space-y-1">
        <div className="text-destructive text-sm font-semibold">推理过程加载失败</div>
        <div className="text-muted-foreground text-xs leading-5 whitespace-pre-wrap">{error}</div>
      </div>
    </div>
  )
}