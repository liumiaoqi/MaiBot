import { useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2, XCircle } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import type { TestConnectionResult, ModelTestResult } from '@/lib/config-api'

export interface ConnectionTestBadgeProps {
  /** 厂商连接测试结果 */
  result?: TestConnectionResult
  /** 是否正在测试 */
  isTesting?: boolean
  /** 模型测试结果（可选——模型测试详情弹窗） */
  modelResult?: ModelTestResult
  /** 尺寸 */
  size?: 'sm' | 'md'
}

/** 连接测试状态徽章——绿=Key 有效/蓝=网络通/红=失败 + 详情弹窗 */
export function ConnectionTestBadge({
  result,
  isTesting = false,
  modelResult,
  size = 'sm',
}: ConnectionTestBadgeProps) {
  const [detailOpen, setDetailOpen] = useState(false)

  const iconSize = size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4'
  const badgeSize = size === 'sm' ? 'h-6 w-6' : 'h-7 w-7'

  if (isTesting) {
    return (
      <span
        className={`inline-flex items-center justify-center rounded ${badgeSize} bg-muted`}
        title="正在测试连接"
        aria-label="正在测试连接"
        data-testid="connection-test-testing"
      >
        <Loader2 className={`${iconSize} animate-spin`} />
      </span>
    )
  }

  if (!result) {
    return (
      <span
        className={`inline-flex items-center justify-center rounded ${badgeSize} border border-muted-foreground/40 bg-transparent`}
        title="未测试"
        aria-label="未测试：尚未执行连接测试"
        data-testid="connection-test-idle"
      />
    )
  }

  let badge: { color: string; icon: React.ReactNode; description: string; testid: string }

  if (result.network_ok) {
    if (result.api_key_valid === true) {
      badge = {
        color: 'bg-green-600 hover:bg-green-700',
        icon: <CheckCircle2 className={iconSize} />,
        description: `连接正常：网络可访问，API Key 有效${result.latency_ms != null ? `，延迟 ${result.latency_ms}ms` : ''}`,
        testid: 'connection-test-success',
      }
    } else if (result.api_key_valid === false) {
      badge = {
        color: 'bg-destructive',
        icon: <AlertCircle className={iconSize} />,
        description: result.error ?? '连接异常：网络可访问，但 API Key 无效或已过期',
        testid: 'connection-test-key-invalid',
      }
    } else {
      badge = {
        color: 'bg-blue-600 hover:bg-blue-700',
        icon: <CheckCircle2 className={iconSize} />,
        description: `可访问：网络连接正常，但未确认 API Key 是否有效${result.latency_ms != null ? `，延迟 ${result.latency_ms}ms` : ''}`,
        testid: 'connection-test-network-only',
      }
    }
  } else {
    badge = {
      color: 'bg-destructive',
      icon: <XCircle className={iconSize} />,
      description: result.error ?? '连接失败：无法访问该厂商',
      testid: 'connection-test-failed',
    }
  }

  return (
    <>
      <span
        className={`inline-flex items-center justify-center rounded ${badgeSize} ${badge.color} cursor-pointer text-white`}
        title={badge.description}
        aria-label={badge.description}
        onClick={() => setDetailOpen(true)}
        data-testid={badge.testid}
      >
        {badge.icon}
      </span>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>连接测试详情</DialogTitle>
            <DialogDescription>{badge.description}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">网络状态</span>
              <span>{result.network_ok ? '可访问' : '不可访问'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">API Key</span>
              <span>
                {result.api_key_valid === true ? '有效' : result.api_key_valid === false ? '无效' : '未验证'}
              </span>
            </div>
            {result.latency_ms != null && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">延迟</span>
                <span>{result.latency_ms}ms</span>
              </div>
            )}
            {result.http_status != null && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">HTTP 状态码</span>
                <span>{result.http_status}</span>
              </div>
            )}
            {result.error && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">错误信息</span>
                <span className="text-destructive">{result.error}</span>
              </div>
            )}
            {modelResult && (
              <>
                <div className="border-t pt-2 mt-2">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">模型名称</span>
                    <span>{modelResult.model_name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">工具调用</span>
                    <span>{modelResult.tool_call_ok ? '支持' : '不支持'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">视觉能力</span>
                    <span>{modelResult.visual_tested ? '已测试' : '未测试'}</span>
                  </div>
                  {modelResult.total_tokens > 0 && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Token 总量</span>
                      <span>{modelResult.total_tokens}</span>
                    </div>
                  )}
                </div>
                {modelResult.response && (
                  <div className="mt-2">
                    <span className="text-muted-foreground">响应内容</span>
                    <pre className="mt-1 rounded bg-muted p-2 text-xs whitespace-pre-wrap">{modelResult.response}</pre>
                  </div>
                )}
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}