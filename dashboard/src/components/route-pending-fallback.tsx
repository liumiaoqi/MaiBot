import { ThinkingIllustration } from '@/components/ui/thinking-illustration'

export function RoutePendingFallback() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="rounded-xl border bg-card px-6 py-4 shadow-sm">
        <ThinkingIllustration size="lg" />
      </div>
    </div>
  )
}
