import { useEffect, useState } from 'react'

import { getDashboardVersionStatus, type DashboardVersionStatus } from '@/lib/system-api'
import { cn } from '@/lib/utils'
import { APP_VERSION, formatVersion } from '@/lib/version'

interface LogoAreaProps {
  sidebarOpen: boolean
}

export function LogoArea({ sidebarOpen }: LogoAreaProps) {
  const [versionStatus, setVersionStatus] = useState<DashboardVersionStatus | null>(null)

  useEffect(() => {
    let mounted = true

    const loadVersionStatus = async () => {
      try {
        const status = await getDashboardVersionStatus(APP_VERSION)
        if (mounted) {
          setVersionStatus(status)
        }
      } catch (error) {
        console.debug('检查 WebUI 版本更新失败:', error)
      }
    }

    void loadVersionStatus()

    return () => {
      mounted = false
    }
  }, [])

  const hasUpdate = versionStatus?.has_update === true && Boolean(versionStatus.latest_version)

  return (
    <div className="flex h-20 items-center border-b px-4">
      <div
        className={cn(
          'relative flex items-center justify-center flex-1 transition-all overflow-hidden',
          // 移动端始终完整显示,桌面端根据 sidebarOpen 切换
          'lg:flex-1',
          !sidebarOpen && 'lg:flex-none lg:w-8'
        )}
      >
        {/* 移动端始终显示完整 Logo，桌面端根据 sidebarOpen 切换 */}
        <div className={cn(
          "flex min-w-0 flex-col items-start justify-center gap-1",
          !sidebarOpen && "lg:hidden"
        )}>
          <span className="max-w-full truncate whitespace-nowrap text-xl font-bold text-primary-gradient">
            MaiBot WebUI
          </span>
          <div className="flex max-w-full items-center gap-2 overflow-hidden">
            <span className="shrink-0 whitespace-nowrap text-sm font-semibold text-primary/70">
              {formatVersion()}
            </span>
            {hasUpdate && (
              <a
                href={versionStatus?.pypi_url}
                target="_blank"
                rel="noopener noreferrer"
                className={cn(
                  "inline-flex h-5 min-w-0 items-center rounded-md border border-amber-400/50 px-2",
                  "bg-amber-400/10 text-[11px] font-semibold text-amber-700",
                  "transition-colors hover:bg-amber-400/20 dark:text-amber-300"
                )}
              >
                <span className="truncate">有更新 v{versionStatus?.latest_version}</span>
              </a>
            )}
          </div>
          {false && hasUpdate && (
            <a
              href={versionStatus?.pypi_url}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                "inline-flex h-5 items-center rounded-md border border-amber-400/50 px-2",
                "bg-amber-400/10 text-[11px] font-semibold text-amber-700",
                "transition-colors hover:bg-amber-400/20 dark:text-amber-300"
              )}
            >
              有更新 v{versionStatus?.latest_version}
            </a>
          )}
          <div className="hidden">
            <span className="font-bold text-xl text-primary-gradient whitespace-nowrap">MaiBot WebUI</span>
            <span className="text-base font-semibold text-primary/70 whitespace-nowrap">
              {formatVersion()}
            </span>
          </div>
        </div>
        {/* 折叠时的 Logo - 仅桌面端显示 */}
        {!sidebarOpen && (
          <span className="hidden lg:block font-bold text-primary-gradient text-2xl">M</span>
        )}
      </div>
    </div>
  )
}
