import { useState, useRef, useEffect, useCallback } from 'react'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useToast } from '@/hooks/use-toast'
import { chatWsClient } from '@/lib/chat-ws-client'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import { cn } from '@/lib/utils'
import { Bot, Edit2, Loader2, RefreshCw, User, Send, Wifi, WifiOff, UserCircle2 } from 'lucide-react'

import { ChatTabBar } from './ChatTabBar'
import { RenderMessageContent } from './MessageRenderer'
import type { ChatTab, ChatMessage, PersonInfo, PlatformInfo, SavedVirtualTab, VirtualIdentityConfig, WsMessage } from './types'
import { getOrCreateUserId, getStoredUserName, getSavedVirtualTabs, saveUserName, saveVirtualTabs } from './utils'
import { VirtualIdentityDialog } from './VirtualIdentityDialog'

export function ChatPage() {
  // 默认 WebUI 标签页
  const defaultTab: ChatTab = {
    id: 'webui-default',
    type: 'webui',
    label: 'WebUI',
    messages: [],
    isConnected: false,
    isTyping: false,
    sessionInfo: {},
  }

  // 从存储中恢复虚拟标签页
  const initializeTabs = (): ChatTab[] => {
    const savedVirtualTabs = getSavedVirtualTabs()
    const restoredTabs: ChatTab[] = savedVirtualTabs.map(saved => {
      // 确保 virtualConfig 有 groupId（兼容旧数据）
      const config = saved.virtualConfig
      if (!config.groupId && config.platform && config.userId) {
        config.groupId = `webui_virtual_group_${config.platform}_${config.userId}`
      }
      return {
        id: saved.id,
        type: 'virtual' as const,
        label: saved.label,
        virtualConfig: config,
        messages: [],
        isConnected: false,
        isTyping: false,
        sessionInfo: {},
      }
    })
    return [defaultTab, ...restoredTabs]
  }

  // 多标签页状态
  const [tabs, setTabs] = useState<ChatTab[]>(initializeTabs)
  const [activeTabId, setActiveTabId] = useState('webui-default')
  
  // 当前活动标签页
  const activeTab = tabs.find(t => t.id === activeTabId) || tabs[0]
  
  // 通用状态
  const [inputValue, setInputValue] = useState('')
  const [isConnecting, setIsConnecting] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(true)
  const [userName, setUserName] = useState(getStoredUserName())
  const [isEditingName, setIsEditingName] = useState(false)
  const [tempUserName, setTempUserName] = useState('')
  
  // 虚拟身份配置对话框状态
  const [showVirtualConfig, setShowVirtualConfig] = useState(false)
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([])
  const [persons, setPersons] = useState<PersonInfo[]>([])
  const [isLoadingPlatforms, setIsLoadingPlatforms] = useState(false)
  const [isLoadingPersons, setIsLoadingPersons] = useState(false)
  const [personSearchQuery, setPersonSearchQuery] = useState('')
  const [tempVirtualConfig, setTempVirtualConfig] = useState<VirtualIdentityConfig>({
    platform: '',
    personId: '',
    userId: '',
    userName: '',
    groupName: '',
    groupId: '',
  })
  
  // 持久化用户 ID
  const userIdRef = useRef(getOrCreateUserId())
  
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messageIdCounterRef = useRef(0)
  const processedMessagesMapRef = useRef<Map<string, Set<string>>>(new Map())
  const sessionUnsubscribeMapRef = useRef<Map<string, () => void>>(new Map())
  const tabsRef = useRef<ChatTab[]>([])
  const { toast } = useToast()

  useEffect(() => {
    tabsRef.current = tabs
  }, [tabs])

  // 生成唯一消息 ID
  const generateMessageId = (prefix: string) => {
    messageIdCounterRef.current += 1
    return `${prefix}-${Date.now()}-${messageIdCounterRef.current}-${Math.random().toString(36).substr(2, 9)}`
  }

  // 更新指定标签页
  const updateTab = useCallback((tabId: string, updates: Partial<ChatTab>) => {
    setTabs(prev => prev.map(tab => 
      tab.id === tabId ? { ...tab, ...updates } : tab
    ))
  }, [])

  // 向指定标签页添加消息
  const addMessageToTab = useCallback((tabId: string, message: ChatMessage) => {
    setTabs(prev => prev.map(tab => 
      tab.id === tabId ? { ...tab, messages: [...tab.messages, message] } : tab
    ))
  }, [])

  // 滚动到底部
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  // 自动滚动
  useEffect(() => {
    scrollToBottom()
  }, [activeTab?.messages, scrollToBottom])

  // 获取平台列表
  const fetchPlatforms = useCallback(async () => {
    setIsLoadingPlatforms(true)
    try {
      const response = await fetchWithAuth('/api/chat/platforms')
      console.log('[Chat] 平台列表响应:', response.status, response.headers.get('content-type'))
      if (response.ok) {
        const contentType = response.headers.get('content-type')
        if (contentType && contentType.includes('application/json')) {
          const data = await response.json()
          console.log('[Chat] 平台列表数据:', data)
          setPlatforms(data.platforms || [])
        } else {
          const text = await response.text()
          console.error('[Chat] 获取平台列表失败: 非 JSON 响应:', text.substring(0, 200))
          toast({
            title: '连接失败',
            description: '无法连接到后端服务，请确保 MaiBot 已启动',
            variant: 'destructive',
          })
        }
      } else {
        console.error('[Chat] 获取平台列表失败: HTTP', response.status)
        toast({
          title: '获取平台失败',
          description: `服务器返回错误: ${response.status}`,
          variant: 'destructive',
        })
      }
    } catch (e) {
      console.error('[Chat] 获取平台列表失败:', e)
      toast({
        title: '网络错误',
        description: '无法连接到后端服务',
        variant: 'destructive',
      })
    } finally {
      setIsLoadingPlatforms(false)
    }
  }, [toast])

  // 获取用户列表
  const fetchPersons = useCallback(async (platform: string, search?: string) => {
    setIsLoadingPersons(true)
    try {
      const params = new URLSearchParams()
      if (platform) params.append('platform', platform)
      if (search) params.append('search', search)
      params.append('limit', '50')
      
      const response = await fetchWithAuth(`/api/chat/persons?${params.toString()}`)
      if (response.ok) {
        const contentType = response.headers.get('content-type')
        if (contentType && contentType.includes('application/json')) {
          const data = await response.json()
          setPersons(data.persons || [])
        } else {
          console.error('[Chat] 获取用户列表失败: 后端返回非 JSON 响应')
        }
      }
    } catch (e) {
      console.error('[Chat] 获取用户列表失败:', e)
    } finally {
      setIsLoadingPersons(false)
    }
  }, [])

  // 当平台选择变化时获取用户列表
  useEffect(() => {
    if (tempVirtualConfig.platform) {
      fetchPersons(tempVirtualConfig.platform, personSearchQuery)
    }
  }, [tempVirtualConfig.platform, personSearchQuery, fetchPersons])

  const handleSessionMessage = useCallback((
    tabId: string,
    tabType: 'webui' | 'virtual',
    config: VirtualIdentityConfig | undefined,
    data: WsMessage,
  ) => {
    switch (data.type) {
      case 'session_info':
        updateTab(tabId, {
          sessionInfo: {
            session_id: data.session_id,
            user_id: data.user_id,
            user_name: data.user_name,
            bot_name: data.bot_name,
          }
        })
        break

      case 'system':
        addMessageToTab(tabId, {
          id: generateMessageId('sys'),
          type: 'system',
          content: data.content || '',
          timestamp: data.timestamp || Date.now() / 1000,
        })
        break

      case 'user_message': {
        const senderUserId = data.sender?.user_id
        const currentUserId = tabType === 'virtual' && config
          ? config.userId
          : userIdRef.current

        const normalizeSenderId = senderUserId ? senderUserId.replace(/^webui_user_/, '') : ''
        const normalizeCurrentId = currentUserId ? currentUserId.replace(/^webui_user_/, '') : ''
        if (normalizeSenderId && normalizeCurrentId && normalizeSenderId === normalizeCurrentId) {
          break
        }

        const processedSet = processedMessagesMapRef.current.get(tabId) || new Set()
        const contentHash = `user-${data.content}-${Math.floor((data.timestamp || 0) * 1000)}`
        if (processedSet.has(contentHash)) {
          break
        }

        processedSet.add(contentHash)
        processedMessagesMapRef.current.set(tabId, processedSet)
        if (processedSet.size > 100) {
          const firstKey = processedSet.values().next().value
          if (firstKey) processedSet.delete(firstKey)
        }

        addMessageToTab(tabId, {
          id: data.message_id || generateMessageId('user'),
          type: 'user',
          content: data.content || '',
          timestamp: data.timestamp || Date.now() / 1000,
          sender: data.sender,
        })
        break
      }

      case 'bot_message': {
        updateTab(tabId, { isTyping: false })
        const processedSet = processedMessagesMapRef.current.get(tabId) || new Set()
        const contentHash = `bot-${data.content}-${Math.floor((data.timestamp || 0) * 1000)}`
        if (processedSet.has(contentHash)) {
          break
        }

        processedSet.add(contentHash)
        processedMessagesMapRef.current.set(tabId, processedSet)
        if (processedSet.size > 100) {
          const firstKey = processedSet.values().next().value
          if (firstKey) processedSet.delete(firstKey)
        }

        setTabs(prev => prev.map(tab => {
          if (tab.id !== tabId) return tab
          const filteredMessages = tab.messages.filter(msg => msg.type !== 'thinking')
          const newMessage: ChatMessage = {
            id: generateMessageId('bot'),
            type: 'bot',
            content: data.content || '',
            message_type: (data.message_type === 'rich' ? 'rich' : 'text') as 'text' | 'rich',
            segments: data.segments,
            timestamp: data.timestamp || Date.now() / 1000,
            sender: data.sender,
          }
          return {
            ...tab,
            messages: [...filteredMessages, newMessage]
          }
        }))
        break
      }

      case 'typing':
        updateTab(tabId, { isTyping: data.is_typing || false })
        break

      case 'error':
        setTabs(prev => prev.map(tab => {
          if (tab.id !== tabId) return tab
          const filteredMessages = tab.messages.filter(msg => msg.type !== 'thinking')
          return {
            ...tab,
            messages: [...filteredMessages, {
              id: generateMessageId('error'),
              type: 'error' as const,
              content: data.content || '发生错误',
              timestamp: data.timestamp || Date.now() / 1000,
            }]
          }
        }))
        toast({
          title: '错误',
          description: data.content,
          variant: 'destructive',
        })
        break

      case 'history': {
        const historyMessages = data.messages || []
        const processedSet = new Set<string>()
        const formattedMessages: ChatMessage[] = historyMessages.map((msg: {
          id?: string
          content: string
          timestamp: number
          sender_name?: string
          sender_id?: string
          is_bot?: boolean
        }) => {
          const isBot = msg.is_bot || false
          const msgId = msg.id || generateMessageId(isBot ? 'bot' : 'user')
          const contentHash = `${isBot ? 'bot' : 'user'}-${msg.content}-${Math.floor(msg.timestamp * 1000)}`
          processedSet.add(contentHash)
          return {
            id: msgId,
            type: isBot ? 'bot' : 'user' as const,
            content: msg.content,
            timestamp: msg.timestamp,
            sender: {
              name: msg.sender_name || (isBot ? '麦麦' : '用户'),
              user_id: msg.sender_id,
              is_bot: isBot,
            },
          }
        })

        processedMessagesMapRef.current.set(tabId, processedSet)
        updateTab(tabId, { messages: formattedMessages })
        setIsLoadingHistory(false)
        break
      }

      default:
        break
    }
  }, [addMessageToTab, toast, updateTab])

  const ensureSessionListener = useCallback((
    tabId: string,
    tabType: 'webui' | 'virtual',
    config?: VirtualIdentityConfig,
  ) => {
    if (sessionUnsubscribeMapRef.current.has(tabId)) {
      return
    }

    const unsubscribe = chatWsClient.onSessionMessage(tabId, (message) => {
      handleSessionMessage(tabId, tabType, config, message as unknown as WsMessage)
    })
    sessionUnsubscribeMapRef.current.set(tabId, unsubscribe)
  }, [handleSessionMessage])

  const openSessionForTab = useCallback(async (
    tabId: string,
    tabType: 'webui' | 'virtual',
    config?: VirtualIdentityConfig,
  ) => {
    ensureSessionListener(tabId, tabType, config)
    setIsLoadingHistory(true)

    try {
      if (tabType === 'virtual' && config) {
        await chatWsClient.openSession(tabId, {
          user_id: config.userId,
          user_name: config.userName,
          platform: config.platform,
          person_id: config.personId,
          group_name: config.groupName || 'WebUI虚拟群聊',
          group_id: config.groupId,
        })
      } else {
        await chatWsClient.openSession(tabId, {
          user_id: userIdRef.current,
          user_name: userName,
        })
      }

      updateTab(tabId, { isConnected: true })
    } catch (error) {
      console.error(`[Tab ${tabId}] 打开聊天会话失败:`, error)
      setIsLoadingHistory(false)
      toast({
        title: '连接失败',
        description: '无法建立聊天会话，请稍后重试',
        variant: 'destructive',
      })
    }
  }, [ensureSessionListener, toast, updateTab, userName])

  // 用于追踪组件是否已卸载
  const isUnmountedRef = useRef(false)

  // 初始化连接（默认 WebUI 标签页）
  useEffect(() => {
    isUnmountedRef.current = false

    const unsubscribeConnection = chatWsClient.onConnectionChange((connected) => {
      if (isUnmountedRef.current) {
        return
      }

      setTabs(prev => prev.map(tab => ({
        ...tab,
        isConnected: connected,
      })))
    })

    const unsubscribeStatus = chatWsClient.onStatusChange((status) => {
      if (!isUnmountedRef.current) {
        setIsConnecting(status === 'connecting')
      }
    })

    tabs.forEach(tab => {
      processedMessagesMapRef.current.set(tab.id, new Set())
      void openSessionForTab(tab.id, tab.type, tab.virtualConfig)
    })

    return () => {
      isUnmountedRef.current = true
      unsubscribeConnection()
      unsubscribeStatus()

      sessionUnsubscribeMapRef.current.forEach((unsubscribe) => {
        unsubscribe()
      })
      sessionUnsubscribeMapRef.current.clear()

      tabsRef.current.forEach(tab => {
        void chatWsClient.closeSession(tab.id)
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 发送消息到当前活动标签页
  const sendMessage = useCallback(async () => {
    if (!inputValue.trim() || !activeTab?.isConnected) {
      return
    }

    const displayName = activeTab?.type === 'virtual' 
      ? activeTab.virtualConfig?.userName || userName
      : userName

    const messageContent = inputValue.trim()
    const currentTimestamp = Date.now() / 1000

    // 添加到去重缓存，防止服务器广播回来的消息重复显示
    const processedSet = processedMessagesMapRef.current.get(activeTabId) || new Set()
    const contentHash = `user-${messageContent}-${Math.floor(currentTimestamp * 1000)}`
    processedSet.add(contentHash)
    processedMessagesMapRef.current.set(activeTabId, processedSet)
    
    if (processedSet.size > 100) {
      const firstKey = processedSet.values().next().value
      if (firstKey) processedSet.delete(firstKey)
    }

    // 先添加用户消息（立即显示）
    const userMessage: ChatMessage = {
      id: generateMessageId('user'),
      type: 'user',
      content: messageContent,
      timestamp: currentTimestamp,
      sender: {
        name: displayName,
        is_bot: false,
      }
    }
    addMessageToTab(activeTabId, userMessage)

    // 再添加"思考中"占位消息
    const thinkingMessage: ChatMessage = {
      id: generateMessageId('thinking'),
      type: 'thinking',
      content: '',
      timestamp: currentTimestamp + 0.001, // 稍微晚一点确保顺序
      sender: {
        name: activeTab?.sessionInfo.bot_name || '麦麦',
        is_bot: true,
      }
    }
    addMessageToTab(activeTabId, thinkingMessage)

    setInputValue('')

    try {
      await chatWsClient.sendMessage(activeTabId, messageContent, displayName)
    } catch (error) {
      console.error('发送聊天消息失败:', error)
      setTabs(prev => prev.map(tab => {
        if (tab.id !== activeTabId) return tab
        return {
          ...tab,
          isTyping: false,
          messages: tab.messages.filter(msg => msg.type !== 'thinking')
        }
      }))
      toast({
        title: '发送失败',
        description: '当前聊天会话不可用，请稍后重试',
        variant: 'destructive',
      })
    }
  }, [activeTab, activeTabId, addMessageToTab, inputValue, toast, userName])

  // 处理键盘事件
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void sendMessage()
    }
  }

  // 处理昵称编辑
  const startEditingName = () => {
    setTempUserName(userName)
    setIsEditingName(true)
  }

  const saveEditedName = () => {
    const newName = tempUserName.trim() || 'WebUI用户'
    setUserName(newName)
    saveUserName(newName)
    setIsEditingName(false)

    if (activeTab?.isConnected) {
      void chatWsClient.updateNickname(activeTabId, newName)
    }
  }

  const cancelEditingName = () => {
    setTempUserName('')
    setIsEditingName(false)
  }

  // 格式化时间
  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp * 1000)
    return date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  // 重新连接当前标签页
  const handleReconnect = () => {
    void chatWsClient.restart()
  }

  // 打开虚拟身份配置对话框（新建标签页用）
  const openVirtualConfig = () => {
    setTempVirtualConfig({
      platform: '',
      personId: '',
      userId: '',
      userName: '',
      groupName: '',
      groupId: '',
    })
    setPersonSearchQuery('')
    fetchPlatforms()
    setShowVirtualConfig(true)
  }

  // 创建新的虚拟身份标签页
  const createVirtualTab = () => {
    if (!tempVirtualConfig.platform || !tempVirtualConfig.personId) {
      toast({
        title: '配置不完整',
        description: '请选择平台和用户',
        variant: 'destructive',
      })
      return
    }
    
    // 生成稳定的虚拟群 ID（基于平台和用户 ID，不包含时间戳）
    const stableGroupId = `webui_virtual_group_${tempVirtualConfig.platform}_${tempVirtualConfig.userId}`
    
    // 生成新标签页ID
    const newTabId = `virtual-${tempVirtualConfig.platform}-${tempVirtualConfig.userId}-${Date.now()}`
    const tabLabel = tempVirtualConfig.userName || tempVirtualConfig.userId
    
    // 创建新标签页，包含稳定的 groupId
    const newTab: ChatTab = {
      id: newTabId,
      type: 'virtual',
      label: tabLabel,
      virtualConfig: { 
        ...tempVirtualConfig,
        groupId: stableGroupId,
      },
      messages: [],
      isConnected: false,
      isTyping: false,
      sessionInfo: {},
    }
    
    setTabs(prev => {
      const newTabs = [...prev, newTab]
      // 保存虚拟标签页到 localStorage
      const virtualTabsToSave: SavedVirtualTab[] = newTabs
        .filter(t => t.type === 'virtual' && t.virtualConfig)
        .map(t => ({
          id: t.id,
          label: t.label,
          virtualConfig: t.virtualConfig!,
          createdAt: Date.now(),
        }))
      saveVirtualTabs(virtualTabsToSave)
      return newTabs
    })
    setActiveTabId(newTabId)
    setShowVirtualConfig(false)
    
    // 初始化去重缓存
    processedMessagesMapRef.current.set(newTabId, new Set())
    
    void openSessionForTab(newTabId, 'virtual', {
      ...tempVirtualConfig,
      groupId: stableGroupId,
    })
    
    toast({
      title: '虚拟身份标签页',
      description: `已创建 ${tabLabel} 的对话`,
    })
  }

  // 关闭标签页
  const closeTab = (tabId: string, e?: React.MouseEvent | React.KeyboardEvent) => {
    e?.stopPropagation()
    
    // 不能关闭默认 WebUI 标签页
    if (tabId === 'webui-default') {
      return
    }

    const unsubscribe = sessionUnsubscribeMapRef.current.get(tabId)
    if (unsubscribe) {
      unsubscribe()
      sessionUnsubscribeMapRef.current.delete(tabId)
    }

    void chatWsClient.closeSession(tabId)
    
    // 清理去重缓存
    processedMessagesMapRef.current.delete(tabId)
    
    // 移除标签页并更新存储
    setTabs(prev => {
      const newTabs = prev.filter(t => t.id !== tabId)
      // 更新 localStorage 中的虚拟标签页
      const virtualTabsToSave: SavedVirtualTab[] = newTabs
        .filter(t => t.type === 'virtual' && t.virtualConfig)
        .map(t => ({
          id: t.id,
          label: t.label,
          virtualConfig: t.virtualConfig!,
          createdAt: Date.now(),
        }))
      saveVirtualTabs(virtualTabsToSave)
      return newTabs
    })
    
    // 如果关闭的是当前标签页，切换到默认标签页
    if (activeTabId === tabId) {
      setActiveTabId('webui-default')
    }
  }

  // 切换标签页
  const switchTab = (tabId: string) => {
    setActiveTabId(tabId)
  }

  // 选择用户
  const selectPerson = (person: PersonInfo) => {
    setTempVirtualConfig(prev => ({
      ...prev,
      personId: person.person_id,
      userId: person.user_id,
      userName: person.nickname || person.person_name,
    }))
  }

  return (
    <div className="h-full flex flex-col">
      {/* 虚拟身份配置对话框 */}
      <VirtualIdentityDialog
        open={showVirtualConfig}
        onOpenChange={setShowVirtualConfig}
        platforms={platforms}
        persons={persons}
        isLoadingPlatforms={isLoadingPlatforms}
        isLoadingPersons={isLoadingPersons}
        personSearchQuery={personSearchQuery}
        setPersonSearchQuery={setPersonSearchQuery}
        tempVirtualConfig={tempVirtualConfig}
        setTempVirtualConfig={setTempVirtualConfig}
        onSelectPerson={selectPerson}
        onCreateVirtualTab={createVirtualTab}
      />

      {/* 标签页栏 */}
      <ChatTabBar
        tabs={tabs}
        activeTabId={activeTabId}
        onSwitch={switchTab}
        onClose={closeTab}
        onAddVirtual={openVirtualConfig}
      />

      {/* 头部信息栏 */}
      <div className="shrink-0 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="p-3 sm:p-4 max-w-4xl mx-auto">
          {/* 标题行 */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              <Avatar className="h-8 w-8 sm:h-10 sm:w-10 shrink-0">
                <AvatarFallback className="bg-primary/10 text-primary">
                  <Bot className="h-4 w-4 sm:h-5 sm:w-5" />
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0">
                <h1 className="text-base sm:text-lg font-semibold truncate">
                  {activeTab?.sessionInfo.bot_name || '麦麦'}
                </h1>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  {activeTab?.isConnected ? (
                    <>
                      <Wifi className="h-3 w-3 text-green-500" />
                      <span className="text-green-600 dark:text-green-400">已连接</span>
                    </>
                  ) : isConnecting ? (
                    <>
                      <Loader2 className="h-3 w-3 animate-spin" />
                      <span>连接中...</span>
                    </>
                  ) : (
                    <>
                      <WifiOff className="h-3 w-3 text-red-500" />
                      <span className="text-red-600 dark:text-red-400">未连接</span>
                    </>
                  )}
                </div>
              </div>
            </div>
            
            {/* 右侧操作按钮 */}
            <div className="flex items-center gap-1 shrink-0">
              {isLoadingHistory && (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={handleReconnect}
                disabled={isConnecting}
                title="重新连接"
              >
                <RefreshCw className={cn('h-4 w-4', isConnecting && 'animate-spin')} />
              </Button>
            </div>
          </div>
          
          {/* 用户身份（桌面端显示更多信息） */}
          <div className="hidden sm:flex items-center gap-2 mt-2 text-sm text-muted-foreground">
            {activeTab?.type === 'virtual' && activeTab.virtualConfig ? (
              <>
                <UserCircle2 className="h-3 w-3 text-primary" />
                <span>虚拟身份：</span>
                <span className="font-medium text-primary">{activeTab.virtualConfig.userName}</span>
                <span className="text-xs">({activeTab.virtualConfig.platform})</span>
                {activeTab.virtualConfig.groupName && (
                  <>
                    <span className="mx-1">·</span>
                    <span className="text-xs">群：{activeTab.virtualConfig.groupName}</span>
                  </>
                )}
              </>
            ) : (
              <>
                <User className="h-3 w-3" />
                <span>当前身份：</span>
                {isEditingName ? (
                  <div className="flex items-center gap-2">
                    <Input
                      value={tempUserName}
                      onChange={(e) => setTempUserName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveEditedName()
                        if (e.key === 'Escape') cancelEditingName()
                      }}
                      className="h-7 w-32"
                      placeholder="输入昵称"
                      autoFocus
                    />
                    <Button size="sm" variant="ghost" className="h-7 px-2" onClick={saveEditedName}>
                      保存
                    </Button>
                    <Button size="sm" variant="ghost" className="h-7 px-2" onClick={cancelEditingName}>
                      取消
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1">
                    <span className="font-medium text-foreground">{userName}</span>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 w-6 p-0"
                      onClick={startEditingName}
                      title="修改昵称"
                    >
                      <Edit2 className="h-3 w-3" />
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* 消息列表区域 */}
      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="p-3 sm:p-4 max-w-4xl mx-auto space-y-3 sm:space-y-4">
            {activeTab?.messages.length === 0 && !isLoadingHistory && (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Bot className="h-12 w-12 mb-4 opacity-50" />
                <p className="text-sm">开始与 {activeTab?.sessionInfo.bot_name || '麦麦'} 对话吧！</p>
              </div>
            )}
            
            {activeTab?.messages.map((message) => (
              <div
                key={message.id}
                className={cn(
                  'flex gap-2 sm:gap-3',
                  message.type === 'user' && 'flex-row-reverse',
                  message.type === 'system' && 'justify-center',
                  message.type === 'error' && 'justify-center'
                )}
              >
                {/* 系统消息 */}
                {message.type === 'system' && (
                  <div className="text-xs text-muted-foreground bg-muted/50 px-3 py-1 rounded-full max-w-[90%]">
                    {message.content}
                  </div>
                )}

                {/* 错误消息 */}
                {message.type === 'error' && (
                  <div className="text-xs text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30 px-3 py-1 rounded-full max-w-[90%]">
                    {message.content}
                  </div>
                )}

                {/* 思考中占位消息 */}
                {message.type === 'thinking' && (
                  <>
                    <Avatar className="h-7 w-7 sm:h-8 sm:w-8 shrink-0">
                      <AvatarFallback className="bg-primary/10 text-primary">
                        <Bot className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      </AvatarFallback>
                    </Avatar>
                    <div className="flex flex-col gap-1 max-w-[75%] sm:max-w-[70%]">
                      <div className="flex items-center gap-2 text-[10px] sm:text-xs text-muted-foreground">
                        <span className="hidden sm:inline">{message.sender?.name || activeTab?.sessionInfo.bot_name}</span>
                      </div>
                      <div className="bg-muted rounded-2xl rounded-tl-sm px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex gap-1">
                            <span className="w-2 h-2 bg-primary/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                            <span className="w-2 h-2 bg-primary/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                            <span className="w-2 h-2 bg-primary/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                          </div>
                          <span className="text-xs text-muted-foreground ml-1">思考中...</span>
                        </div>
                      </div>
                    </div>
                  </>
                )}

                {/* 用户/机器人消息 */}
                {(message.type === 'user' || message.type === 'bot') && (
                  <>
                    <Avatar className="h-7 w-7 sm:h-8 sm:w-8 shrink-0">
                      <AvatarFallback
                        className={cn(
                          'text-xs',
                          message.type === 'bot'
                            ? 'bg-primary/10 text-primary'
                            : 'bg-secondary text-secondary-foreground'
                        )}
                      >
                        {message.type === 'bot' ? (
                          <Bot className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                        ) : (
                          <User className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                        )}
                      </AvatarFallback>
                    </Avatar>
                    <div
                      className={cn(
                        'flex flex-col gap-1 max-w-[75%] sm:max-w-[70%]',
                        message.type === 'user' && 'items-end'
                      )}
                    >
                      <div className="flex items-center gap-2 text-[10px] sm:text-xs text-muted-foreground">
                        <span className="hidden sm:inline">{message.sender?.name || (message.type === 'bot' ? activeTab?.sessionInfo.bot_name : userName)}</span>
                        <span>{formatTime(message.timestamp)}</span>
                      </div>
                      <div
                        className={cn(
                          'rounded-2xl px-3 py-2 text-sm break-words',
                          message.type === 'bot'
                            ? 'bg-muted rounded-tl-sm'
                            : 'bg-primary text-primary-foreground rounded-tr-sm'
                        )}
                      >
                        <RenderMessageContent message={message} isBot={message.type === 'bot'} />
                      </div>
                    </div>
                  </>
                )}
              </div>
            ))}

            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>
      </div>

      {/* 输入区域 - 固定在底部 */}
      <div className="shrink-0 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="p-3 sm:p-4 max-w-4xl mx-auto">
          <div className="flex gap-2">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={activeTab?.isConnected ? '输入消息...' : '等待连接...'}
              disabled={!activeTab?.isConnected}
              className="flex-1 h-10 sm:h-10"
            />
            <Button
              onClick={() => { void sendMessage() }}
              disabled={!activeTab?.isConnected || !inputValue.trim()}
              size="icon"
              className="h-10 w-10 shrink-0"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
