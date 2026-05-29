import { useState, useRef, useEffect, useMemo } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { Card } from '@/components/ui/card'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Search, RefreshCw, Download, Filter, Trash2, Pause, Play, Calendar as CalendarIcon, X, Type, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import { logWebSocket, type LogEntry } from '@/lib/log-websocket'
import { format } from 'date-fns'
import { zhCN } from 'date-fns/locale'

// 字号配置
type FontSize = 'xs' | 'sm' | 'base'
type LogLevelFilter = LogEntry['level'] | 'all'

const fontSizeConfig: Record<FontSize, { label: string; rowHeight: number; class: string }> = {
  xs: { label: '小', rowHeight: 28, class: 'text-[10px] sm:text-xs' },
  sm: { label: '中', rowHeight: 36, class: 'text-xs sm:text-sm' },
  base: { label: '大', rowHeight: 44, class: 'text-sm sm:text-base' },
}

const logColumnLayoutConfig: Record<
  FontSize,
  { gapClass: string; levelClass: string; moduleClass: string; timestampClass: string }
> = {
  xs: {
    gapClass: 'gap-1.5',
    timestampClass: 'w-[60px] lg:w-[60px]',
    levelClass: 'w-[30px] lg:w-[30px]',
    moduleClass: 'w-[90px] lg:w-[90px]',
  },
  sm: {
    gapClass: 'gap-2',
    timestampClass: 'w-[76px] lg:w-[76px]',
    levelClass: 'w-[38px] lg:w-[38px]',
    moduleClass: 'w-[112px] lg:w-[112px]',
  },
  base: {
    gapClass: 'gap-2.5',
    timestampClass: 'w-[92px] lg:w-[92px]',
    levelClass: 'w-[46px] lg:w-[46px]',
    moduleClass: 'w-[136px] lg:w-[136px]',
  },
}

const levelPriority: Record<LogEntry['level'], number> = {
  DEBUG: 10,
  INFO: 20,
  WARNING: 30,
  ERROR: 40,
  CRITICAL: 50,
}

function formatLogTimestamp(timestamp: string) {
  const normalized = timestamp.trim()
  const match = normalized.match(/^(\d{4})-(\d{2})-(\d{2})([ T].*)$/)
  if (!match) {
    return timestamp
  }

  return `${match[2]}-${match[3]}${match[4].replace(/^T/, ' ')}`
}

function getModuleTextStyle(log: LogEntry) {
  if (!log.moduleColor) {
    return undefined
  }

  return {
    color: log.moduleColor,
    fontWeight: log.moduleBold ? 700 : undefined,
  }
}

function formatLogLevel(level: LogEntry['level']) {
  return level.slice(0, 4)
}

export function LogViewerPage() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [levelFilter, setLevelFilter] = useState<LogLevelFilter>('INFO')
  const [moduleFilter, setModuleFilter] = useState<string>('all')
  const [dateFrom, setDateFrom] = useState<Date | undefined>(undefined)
  const [dateTo, setDateTo] = useState<Date | undefined>(undefined)
  const [autoScroll, setAutoScroll] = useState(true)
  const [connected, setConnected] = useState(false)
  const [fontSize, setFontSize] = useState<FontSize>('xs') // 默认使用小字号以显示更多信息
  const [lineSpacing, setLineSpacing] = useState(4) // 行间距，默认4px（紧凑）
  const [filtersOpen, setFiltersOpen] = useState(false) // 控制折叠面板，默认折叠
  const parentRef = useRef<HTMLDivElement>(null)

  // 订阅全局 WebSocket 连接
  useEffect(() => {
    // 初始化时加载缓存的日志
    const cachedLogs = logWebSocket.getAllLogs()
    setLogs(cachedLogs)
    
    // 订阅日志消息 - 直接使用全局缓存而不是组件状态
    const unsubscribeLogs = logWebSocket.onLog(() => {
      // 每次收到新日志，重新从全局缓存加载
      setLogs(logWebSocket.getAllLogs())
    })

    // 订阅连接状态
    const unsubscribeConnection = logWebSocket.onConnectionChange((isConnected) => {
      setConnected(isConnected)
    })

    // 清理订阅
    return () => {
      unsubscribeLogs()
      unsubscribeConnection()
    }
  }, [])

  // 获取所有唯一的模块名（过滤掉空字符串）
  const uniqueModules = useMemo(() => {
    const modules = new Set(logs.map(log => log.module).filter(m => m && m.trim() !== ''))
    return Array.from(modules).sort()
  }, [logs])

  // 日志级别颜色映射
  const getLevelColor = (level: LogEntry['level']) => {
    switch (level) {
      case 'DEBUG':
        return 'text-muted-foreground'
      case 'INFO':
        return 'text-blue-500 dark:text-blue-400'
      case 'WARNING':
        return 'text-yellow-600 dark:text-yellow-500'
      case 'ERROR':
        return 'text-red-600 dark:text-red-500'
      case 'CRITICAL':
        return 'text-red-700 dark:text-red-400 font-bold'
      default:
        return 'text-foreground'
    }
  }

  // 刷新日志（刷新页面）
  const handleRefresh = () => {
    window.location.reload()
  }

  // 清空日志
  const handleClear = () => {
    logWebSocket.clearLogs() // 清空全局缓存
    setLogs([])
  }

  // 导出日志为 TXT 格式
  const handleExport = () => {
    // 格式化日志为文本
    const logText = filteredLogs.map(log => 
      `${log.timestamp} [${log.level.padEnd(8)}] [${log.module}] ${log.message}`
    ).join('\n')
    
    const dataBlob = new Blob([logText], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `logs-${format(new Date(), 'yyyy-MM-dd-HHmmss')}.txt`
    link.click()
    URL.revokeObjectURL(url)
  }

  // 切换自动滚动
  const toggleAutoScroll = () => {
    setAutoScroll(!autoScroll)
  }

  // 清除时间筛选
  const clearDateFilter = () => {
    setDateFrom(undefined)
    setDateTo(undefined)
  }

  // 过滤日志
  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      // 搜索过滤
      const matchesSearch =
        searchQuery === '' ||
        log.message.toLowerCase().includes(searchQuery.toLowerCase()) ||
        log.module.toLowerCase().includes(searchQuery.toLowerCase())
      
      // 级别过滤：选择某个级别时显示该级别及以上的日志
      const matchesLevel =
        levelFilter === 'all' ||
        levelPriority[log.level] >= levelPriority[levelFilter]
      
      // 模块过滤
      const matchesModule = moduleFilter === 'all' || log.module === moduleFilter
      
      // 时间过滤
      let matchesDate = true
      if (dateFrom || dateTo) {
        const logDate = new Date(log.timestamp)
        if (dateFrom) {
          const fromDate = new Date(dateFrom)
          fromDate.setHours(0, 0, 0, 0)
          matchesDate = matchesDate && logDate >= fromDate
        }
        if (dateTo) {
          const toDate = new Date(dateTo)
          toDate.setHours(23, 59, 59, 999)
          matchesDate = matchesDate && logDate <= toDate
        }
      }
      
      return matchesSearch && matchesLevel && matchesModule && matchesDate
    })
  }, [logs, searchQuery, levelFilter, moduleFilter, dateFrom, dateTo])

  // 虚拟滚动配置 - 根据字号和行间距动态计算行高
  const estimatedRowHeight = fontSizeConfig[fontSize].rowHeight + lineSpacing
  const logColumnLayout = logColumnLayoutConfig[fontSize]
  
  const rowVirtualizer = useVirtualizer({
    count: filteredLogs.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimatedRowHeight,
    overscan: 50, // 增加预渲染数量以减少快速滚动时的空白
  })

  // 用于追踪是否是程序触发的滚动
  const isAutoScrollingRef = useRef(false)
  // 用于追踪上一次的日志数量
  const prevLogCountRef = useRef(filteredLogs.length)

  // 检测用户滚动行为，当用户向上滚动时禁用自动滚动
  useEffect(() => {
    const scrollElement = parentRef.current
    if (!scrollElement) return

    const handleScroll = () => {
      // 如果是程序触发的滚动，忽略
      if (isAutoScrollingRef.current) return

      const { scrollTop, scrollHeight, clientHeight } = scrollElement
      const distanceFromBottom = scrollHeight - scrollTop - clientHeight
      
      // 如果距离底部超过 100px，说明用户在向上查看，禁用自动滚动
      if (distanceFromBottom > 100 && autoScroll) {
        setAutoScroll(false)
      }
      // 如果用户滚动到接近底部（小于 50px），可以重新启用自动滚动
      else if (distanceFromBottom < 50 && !autoScroll) {
        setAutoScroll(true)
      }
    }

    scrollElement.addEventListener('scroll', handleScroll, { passive: true })
    return () => scrollElement.removeEventListener('scroll', handleScroll)
  }, [autoScroll])

  // 自动滚动到底部
  useEffect(() => {
    // 只有在日志数量增加时才滚动（避免删除日志时触发）
    const logCountIncreased = filteredLogs.length > prevLogCountRef.current
    prevLogCountRef.current = filteredLogs.length

    if (autoScroll && filteredLogs.length > 0 && logCountIncreased) {
      isAutoScrollingRef.current = true
      rowVirtualizer.scrollToIndex(filteredLogs.length - 1, {
        align: 'end',
        behavior: 'auto',
      })
      // 稍后重置标志，给滚动事件处理一些时间
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          isAutoScrollingRef.current = false
        })
      })
    }
  }, [filteredLogs.length, autoScroll, rowVirtualizer])

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* 顶部操作面板 - 紧凑设计，默认折叠 */}
      <div className="flex-shrink-0 space-y-2 sm:space-y-3 p-2 sm:p-3 lg:p-4">
        {/* 控制栏 - 可折叠 */}
        <Card className="p-2 sm:p-3">
          <Collapsible open={filtersOpen} onOpenChange={setFiltersOpen}>
            <div className="flex flex-col gap-2">
              {/* 第一行：始终显示 - 搜索、快捷操作、展开按钮 */}
              <div className="flex gap-2">
                {/* 搜索框 */}
                <div className="flex-1 relative min-w-0">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder="搜索日志..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-8 h-8 text-xs sm:text-sm"
                  />
                </div>

                {/* 快捷操作按钮 */}
                <div className="flex gap-1 flex-shrink-0">
                  <Button
                    variant={autoScroll ? 'default' : 'outline'}
                    size="sm"
                    onClick={toggleAutoScroll}
                    className="h-8 px-2"
                    title={autoScroll ? '自动滚动' : '已暂停'}
                  >
                    {autoScroll ? (
                      <Pause className="h-3.5 w-3.5" />
                    ) : (
                      <Play className="h-3.5 w-3.5" />
                    )}
                    <span className="ml-1 text-xs hidden sm:inline">
                      {autoScroll ? '滚动' : '暂停'}
                    </span>
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleClear}
                    className="h-8 px-2"
                    title="清空日志"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    <span className="ml-1 text-xs hidden md:inline">清空</span>
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleExport}
                    className="h-8 px-2 hidden sm:flex"
                    title="导出日志"
                  >
                    <Download className="h-3.5 w-3.5" />
                    <span className="ml-1 text-xs hidden lg:inline">导出</span>
                  </Button>
                  
                  {/* 展开/收起按钮 */}
                  <CollapsibleTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 px-2"
                      title={filtersOpen ? '收起筛选' : '展开筛选'}
                    >
                      <Filter className="h-3.5 w-3.5" />
                      {filtersOpen ? (
                        <ChevronUp className="h-3.5 w-3.5 ml-1" />
                      ) : (
                        <ChevronDown className="h-3.5 w-3.5 ml-1" />
                      )}
                    </Button>
                  </CollapsibleTrigger>
                </div>
              </div>

              {/* 日志数量显示 */}
              <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground -mt-1">
                <div className="flex items-center gap-2">
                  <div
                    className={cn(
                      'h-2 w-2 sm:h-2.5 sm:w-2.5 rounded-full',
                      connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'
                    )}
                  />
                  <span>{connected ? '已连接' : '未连接'}</span>
                </div>
                <div className="text-right">
                  <span className="font-mono">
                    {filteredLogs.length} / {logs.length}
                  </span>
                  <span className="ml-1">条日志</span>
                </div>
              </div>

              {/* 可折叠的筛选区域 */}
              <CollapsibleContent className="space-y-2">
                {/* 级别和模块筛选 */}
                <div className="flex flex-col gap-2 sm:flex-row sm:gap-2">
                  <Select value={levelFilter} onValueChange={(value) => setLevelFilter(value as LogLevelFilter)}>
                    <SelectTrigger className="w-full sm:flex-1 h-8 text-xs">
                      <Filter className="h-3.5 w-3.5 mr-1.5" />
                      <SelectValue placeholder="最低级别" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部级别</SelectItem>
                      <SelectItem value="DEBUG">DEBUG 及以上</SelectItem>
                      <SelectItem value="INFO">INFO 及以上</SelectItem>
                      <SelectItem value="WARNING">WARNING 及以上</SelectItem>
                      <SelectItem value="ERROR">ERROR 及以上</SelectItem>
                      <SelectItem value="CRITICAL">CRITICAL</SelectItem>
                    </SelectContent>
                  </Select>

                  <Select value={moduleFilter} onValueChange={setModuleFilter}>
                    <SelectTrigger className="w-full sm:flex-1 h-8 text-xs">
                      <Filter className="h-3.5 w-3.5 mr-1.5" />
                      <SelectValue placeholder="模块" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部模块</SelectItem>
                      {uniqueModules.map(module => (
                        <SelectItem key={module} value={module}>
                          {module}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* 时间筛选 */}
                <div className="flex flex-col gap-2 sm:flex-row sm:gap-2">
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        className={cn(
                          'w-full sm:flex-1 justify-start text-left font-normal h-8',
                          !dateFrom && 'text-muted-foreground'
                        )}
                      >
                        <CalendarIcon className="mr-1.5 h-3.5 w-3.5" />
                        <span className="text-xs">
                          {dateFrom ? format(dateFrom, 'PP', { locale: zhCN }) : '开始日期'}
                        </span>
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={dateFrom}
                        onSelect={setDateFrom}
                        initialFocus
                        locale={zhCN}
                      />
                    </PopoverContent>
                  </Popover>

                  <Popover>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        className={cn(
                          'w-full sm:flex-1 justify-start text-left font-normal h-8',
                          !dateTo && 'text-muted-foreground'
                        )}
                      >
                        <CalendarIcon className="mr-1.5 h-3.5 w-3.5" />
                        <span className="text-xs">
                          {dateTo ? format(dateTo, 'PP', { locale: zhCN }) : '结束日期'}
                        </span>
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={dateTo}
                        onSelect={setDateTo}
                        initialFocus
                        locale={zhCN}
                      />
                    </PopoverContent>
                  </Popover>

                  {(dateFrom || dateTo) && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={clearDateFilter}
                      className="w-full sm:w-auto h-8"
                    >
                      <X className="h-3.5 w-3.5 sm:mr-1" />
                      <span className="text-xs">清除</span>
                    </Button>
                  )}
                </div>

                {/* 显示设置 */}
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3 pt-2 border-t border-border/50">
                  {/* 字号调整 */}
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Type className="h-3.5 w-3.5" />
                      <span>字号</span>
                    </div>
                    <div className="flex gap-1">
                      {(Object.keys(fontSizeConfig) as FontSize[]).map((size) => (
                        <Button
                          key={size}
                          variant={fontSize === size ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => setFontSize(size)}
                          className="h-6 px-2 text-xs"
                        >
                          {fontSizeConfig[size].label}
                        </Button>
                      ))}
                    </div>
                  </div>

                  {/* 行间距调整 */}
                  <div className="flex items-center gap-2 flex-1 max-w-[200px]">
                    <span className="text-xs text-muted-foreground whitespace-nowrap">行距</span>
                    <Slider
                      value={[lineSpacing]}
                      onValueChange={([value]) => setLineSpacing(value)}
                      min={0}
                      max={12}
                      step={2}
                      className="flex-1"
                    />
                    <span className="text-xs text-muted-foreground w-7">{lineSpacing}px</span>
                  </div>

                  {/* 额外操作按钮（移动端） */}
                  <div className="flex gap-2 sm:hidden">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleRefresh}
                      className="flex-1 h-8"
                    >
                      <RefreshCw className="h-3.5 w-3.5 mr-1" />
                      <span className="text-xs">刷新</span>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleExport}
                      className="flex-1 h-8"
                    >
                      <Download className="h-3.5 w-3.5 mr-1" />
                      <span className="text-xs">导出</span>
                    </Button>
                  </div>
                </div>
              </CollapsibleContent>
            </div>
          </Collapsible>
        </Card>
      </div>

      {/* 日志终端 - 占据剩余所有空间 */}
      <div className="flex-1 min-h-0 px-2 sm:px-3 lg:px-4 pb-2 sm:pb-3 lg:pb-4">
        <Card
          className="h-full overflow-hidden border-[#24170f]/70 dark:border-[#1d120c]/80"
          style={{ backgroundColor: '#633312' }}
        >
          <div 
            ref={parentRef}
            className={cn(
              "h-full overflow-auto selection:bg-[#5a3924] selection:text-[#fff2df]",
              // 自定义滚动条样式
              "[&::-webkit-scrollbar]:w-2.5",
              "[&::-webkit-scrollbar-track]:bg-transparent",
              "[&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full",
              "[&::-webkit-scrollbar-thumb:hover]:bg-border/80"
            )}
            style={{ backgroundColor: '#211607' }}
          >
            <div
              className={cn(
                "p-2 sm:p-3 font-mono relative selection:bg-[#5a3924] selection:text-[#fff2df]",
                fontSizeConfig[fontSize].class
              )}
              style={{
                height: `${rowVirtualizer.getTotalSize()}px`,
                minHeight: '100%',
              }}
            >
              {filteredLogs.length === 0 ? (
                <div className="text-gray-500 dark:text-gray-600 text-center py-8 text-xs sm:text-sm">
                  暂无日志数据
                </div>
              ) : (
                rowVirtualizer.getVirtualItems().map((virtualRow) => {
                  const log = filteredLogs[virtualRow.index]
                  const timestampText = formatLogTimestamp(log.timestamp)
                  const levelText = formatLogLevel(log.level)
                  const moduleTextStyle = getModuleTextStyle(log)
                  return (
                    <div
                      key={virtualRow.key}
                      data-index={virtualRow.index}
                      ref={rowVirtualizer.measureElement}
                      className="absolute top-0 left-0 w-full px-2 sm:px-3"
                      style={{
                        transform: `translateY(${virtualRow.start}px)`,
                        paddingTop: `${lineSpacing / 2}px`,
                        paddingBottom: `${lineSpacing / 2}px`,
                      }}
                    >
                      {/* 移动端：垂直布局 */}
                      <div className="flex flex-col gap-0.5 sm:hidden">
                        {/* 第一行：时间戳和级别 */}
                        <div className="flex items-center gap-2">
                          <span className="text-gray-500 dark:text-gray-600 text-[10px]">
                            {timestampText}
                          </span>
                          <span
                            className={cn(
                              'font-semibold text-[10px]',
                              getLevelColor(log.level)
                            )}
                          >
                            [{levelText}]
                          </span>
                        </div>
                        {/* 第二行：模块名 */}
                        <div
                          className={cn(
                            'truncate text-[10px]',
                            !moduleTextStyle && 'text-cyan-400 dark:text-cyan-500'
                          )}
                          style={moduleTextStyle}
                        >
                          {log.module}
                        </div>
                        {/* 第三行：消息内容 */}
                        <div
                          className={cn(
                            'whitespace-pre-wrap break-words text-[10px]',
                            !moduleTextStyle && 'text-gray-300 dark:text-gray-400'
                          )}
                          style={moduleTextStyle}
                        >
                          {log.message}
                        </div>
                      </div>

                      {/* 平板/桌面端：水平布局 */}
                      <div className={cn('hidden sm:flex items-start', logColumnLayout.gapClass)}>
                        {/* 时间戳 */}
                        <span
                          className={cn(
                            'text-gray-500 dark:text-gray-600 flex-shrink-0',
                            logColumnLayout.timestampClass
                          )}
                        >
                          {timestampText}
                        </span>

                        {/* 日志级别 */}
                        <span
                          className={cn(
                            'flex-shrink-0 font-semibold',
                            logColumnLayout.levelClass,
                            getLevelColor(log.level)
                          )}
                        >
                          [{levelText}]
                        </span>

                        {/* 模块名 */}
                        <span
                          className={cn(
                            'flex-shrink-0 truncate',
                            logColumnLayout.moduleClass,
                            !moduleTextStyle && 'text-cyan-400 dark:text-cyan-500'
                          )}
                          style={moduleTextStyle}
                        >
                          {log.module}
                        </span>

                        {/* 消息内容 */}
                        <span
                          className={cn(
                            'flex-1 whitespace-pre-wrap break-words',
                            !moduleTextStyle && 'text-gray-300 dark:text-gray-400'
                          )}
                          style={moduleTextStyle}
                        >
                          {log.message}
                        </span>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
