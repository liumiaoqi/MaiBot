import { Link } from '@tanstack/react-router'
import { ArrowRight, Info } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'

/**
 * 麦麦适配器配置 —— 禁用页
 *
 * 原页面（{@link import('./adapter').AdapterConfigPage}）的能力已迁移至
 * 「插件配置」中的对应适配器插件。这里保留路由占位并引导用户跳转，
 * 避免误用旧的 TOML 直接编辑路径。
 */
export function AdapterConfigPage() {
  return (
    <ScrollArea className="h-full">
      <div className="mx-auto w-full max-w-3xl space-y-4 p-4 sm:space-y-6 sm:p-6">
        <div>
          <h1 className="text-2xl font-bold sm:text-3xl">麦麦适配器配置</h1>
          <p className="text-muted-foreground mt-1 text-sm sm:mt-2 sm:text-base">
            该界面已停用
          </p>
        </div>

        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>该配置入口已迁移</AlertTitle>
          <AlertDescription>
            适配器现已作为插件管理。请前往「插件配置」找到对应适配器插件（如 Napcat 适配器）进行配置。
          </AlertDescription>
        </Alert>

        <Card>
          <CardHeader>
            <CardTitle>请前往插件配置</CardTitle>
            <CardDescription>
              在插件配置页面中，选择目标适配器插件即可修改其配置项。原适配器 TOML 直接编辑入口已停用，但相关代码与历史配置文件未被删除，可在需要时由开发者手动恢复。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link to="/plugin-config">
                打开插件配置
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </ScrollArea>
  )
}
