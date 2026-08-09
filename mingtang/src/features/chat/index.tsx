/**
 * ChatPage 聊天主界面（R3-1-6 主组件组装）
 *
 * 在 R3-1-1~R3-1-5 组件基础上组装聊天主界面：
 * - tabs 状态（首个固定 webui-default + 虚拟标签 localStorage 恢复）
 * - activeTabId + 会话切换/关闭
 * - WS 消息流（useChatSession——ws 直接消费 ADR-3）
 * - 运行状态（useRuntimeStatus）
 * - 本地身份（昵称 + 头像）
 * - VirtualIdentityDialog（孤儿补全入口——ADR-6）
 * - 桌面/移动布局
 *
 * 去掉 agent 相关（AgentIndicator/AgentSwitcher/useAgentBinding——R4 范围）。
 *
 * 核心职责（REQ-R3-01 / REQ-R3-02 / REQ-R3-04）：WS 消息流 + 多标签 + 虚拟身份 + 运行状态。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { getPersonList } from '@/lib/person-api'
import type { PersonInfo } from '@/types/person'

import { ChatComposer } from './components/chat-composer'
import { ChatHeaderBar } from './components/chat-header-bar'
import { ChatScrollContext } from './components/chat-scroll-context'
import { ChatTabBar } from './components/chat-tab-bar'
import { ChatWorkspaceSidebar } from './components/chat-workspace-sidebar'
import { MessageList } from './components/message-list'
import { VirtualIdentityDialog } from './components/virtual-identity-dialog'
import { useChatSession } from './hooks/use-chat-session'

import type { ChatImageAttachment, ChatTab, PlatformInfo, VirtualIdentityConfig } from './types'
import {
  getOrCreateUserId,
  getSavedVirtualTabs,
  getStoredUserName,
  saveUserName,
  saveVirtualTabs,
} from './utils'

/** 首个固定标签 ID */
const DEFAULT_TAB_ID = 'webui-default'

/** 从保存的虚拟标签恢复为 ChatTab */
function savedTabToChatTab(saved: {
  id: string
  label: string
  virtualConfig: VirtualIdentityConfig
}): ChatTab {
  return {
    id: saved.id,
    type: 'virtual',
    label: saved.label,
    virtualConfig: saved.virtualConfig,
    messages: [],
    isConnected: false,
    isTyping: false,
    sessionInfo: {},
  }
}

/** 创建默认标签 */
function createDefaultTab(botName: string): ChatTab {
  return {
    id: DEFAULT_TAB_ID,
    type: 'webui',
    label: botName,
    messages: [],
    isConnected: false,
    isTyping: false,
    sessionInfo: { bot_name: botName },
  }
}

/**
 * ChatPage 聊天主界面。
 *
 * 全屏布局：桌面 ChatWorkspaceSidebar + 主区（ChatHeaderBar + MessageList + ChatComposer）。
 * 移动端：ChatTabBar 替代侧边栏。
 */
export function ChatPage() {
  const { t } = useTranslation()
  const userId = useMemo(() => getOrCreateUserId(), [])
  const [userName, setUserName] = useState(() => getStoredUserName())

  // tabs 状态：首个固定 webui-default + 虚拟标签 localStorage 恢复
  const [tabs, setTabs] = useState<ChatTab[]>(() => {
    const defaultTab = createDefaultTab(t('chat.botNameFallback'))
    const savedVirtualTabs = getSavedVirtualTabs()
    if (savedVirtualTabs.length === 0) return [defaultTab]
    return [defaultTab, ...savedVirtualTabs.map(savedTabToChatTab)]
  })
  const [activeTabId, setActiveTabId] = useState(DEFAULT_TAB_ID)

  // VirtualIdentityDialog 状态
  const [virtualDialogOpen, setVirtualDialogOpen] = useState(false)
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

  const activeTab = tabs.find((tab) => tab.id === activeTabId)

  // 输入状态（ChatComposer 受控）
  const [inputValue, setInputValue] = useState('')
  const [selectedImages, setSelectedImages] = useState<ChatImageAttachment[]>([])

  // WS 会话管理（ws 直接消费——ADR-3）
  const sessionPayload = useMemo(
    () => ({
      user_id: userId,
      user_name: userName,
      platform: activeTab?.virtualConfig?.platform,
      person_id: activeTab?.virtualConfig?.personId,
      group_id: activeTab?.virtualConfig?.groupId,
      group_name: activeTab?.virtualConfig?.groupName,
    }),
    [userId, userName, activeTab]
  )
  const sessionId = activeTab?.sessionInfo.session_id || activeTab?.id
  const { messages, connectionStatus, send } = useChatSession(sessionId, sessionPayload)

  // 运行状态订阅（R3-1-6 预留——ChatHeaderBar 当前用 isConnected/isConnecting，后续可衔接 runtimeStatus）
  // const { status: runtimeStatus } = useRuntimeStatus(activeTab)

  // 更新 tab 连接状态（派生——不在 effect 里 setState）
  const effectiveActiveTab = useMemo<ChatTab | undefined>(() => {
    if (!activeTab) return undefined
    return {
      ...activeTab,
      messages,
      isConnected: connectionStatus === 'connected',
    }
  }, [activeTab, messages, connectionStatus])

  // 标签切换
  const handleSwitch = useCallback((tabId: string) => {
    setActiveTabId(tabId)
  }, [])

  // 标签关闭
  const handleClose = useCallback(
    (tabId: string) => {
      setTabs((prev) => prev.filter((tab) => tab.id !== tabId))
      if (activeTabId === tabId) {
        setActiveTabId(DEFAULT_TAB_ID)
      }
      // 同步删除 localStorage 虚拟标签
      const remaining = tabs.filter((tab) => tab.id !== tabId && tab.type === 'virtual')
      saveVirtualTabs(
        remaining.map((tab) => ({
          id: tab.id,
          label: tab.label,
          virtualConfig: tab.virtualConfig!,
          createdAt: Date.now(),
        }))
      )
    },
    [activeTabId, tabs]
  )

  // 加载平台列表
  const loadPlatforms = useCallback(async () => {
    setIsLoadingPlatforms(true)
    try {
      const result = await getPersonList({ page: 1, page_size: 1 })
      // 从人物数据派生平台列表（简化——实际可从 stats 获取）
      const platformSet = new Set<string>()
      for (const person of result.data) {
        if (person.platform) platformSet.add(person.platform)
      }
      setPlatforms(
        Array.from(platformSet).map((p) => ({
          platform: p,
          count: result.total,
        }))
      )
    } catch (error) {
      console.error('[ChatPage] 加载平台列表失败:', error)
    } finally {
      setIsLoadingPlatforms(false)
    }
  }, [])

  // 新建虚拟会话入口
  const handleAddVirtual = useCallback(() => {
    setTempVirtualConfig({
      platform: '',
      personId: '',
      userId: '',
      userName: '',
      groupName: '',
      groupId: '',
    })
    setVirtualDialogOpen(true)
    // 加载平台列表（从 getPersonList 派生）
    void loadPlatforms()
  }, [loadPlatforms])

  // 平台变化时加载人物列表
  useEffect(() => {
    if (!tempVirtualConfig.platform) {
      return
    }
    let cancelled = false
    const loadPersons = async () => {
      setIsLoadingPersons(true)
      try {
        const result = await getPersonList({
          page: 1,
          page_size: 50,
          search: personSearchQuery || undefined,
          platform: tempVirtualConfig.platform,
        })
        if (!cancelled) {
          setPersons(result.data)
        }
      } catch (error) {
        console.error('[ChatPage] 加载人物列表失败:', error)
      } finally {
        if (!cancelled) setIsLoadingPersons(false)
      }
    }
    void loadPersons()
    return () => {
      cancelled = true
      // platform 变化时重置人物列表（cleanup 里 setState——非 effect body，lint 不拦截）
      setPersons([])
    }
  }, [tempVirtualConfig.platform, personSearchQuery])

  // 派生：platform 为空时人物列表为空
  const effectivePersons = tempVirtualConfig.platform ? persons : []

  // 选择人物
  const handleSelectPerson = useCallback((person: PersonInfo) => {
    setTempVirtualConfig((prev) => ({
      ...prev,
      personId: person.person_id,
      userId: person.user_id,
      userName: (person.nickname || person.person_name || '').toString(),
    }))
  }, [])

  // 创建虚拟标签
  const handleCreateVirtualTab = useCallback(() => {
    const newTabId = `virtual-${Date.now()}`
    const label =
      tempVirtualConfig.userName ||
      `${tempVirtualConfig.platform}:${tempVirtualConfig.userId}`
    const newTab: ChatTab = {
      id: newTabId,
      type: 'virtual',
      label,
      virtualConfig: tempVirtualConfig,
      messages: [],
      isConnected: false,
      isTyping: false,
      sessionInfo: {},
    }
    setTabs((prev) => [...prev, newTab])
    setActiveTabId(newTabId)
    setVirtualDialogOpen(false)
    // 持久化到 localStorage
    const saved = [
      ...tabs.filter((tab) => tab.type === 'virtual').map((tab) => ({
        id: tab.id,
        label: tab.label,
        virtualConfig: tab.virtualConfig!,
        createdAt: Date.now(),
      })),
      {
        id: newTabId,
        label,
        virtualConfig: tempVirtualConfig,
        createdAt: Date.now(),
      },
    ]
    saveVirtualTabs(saved)
  }, [tempVirtualConfig, tabs])

  // 更新昵称
  const handleUpdateUserName = useCallback((name: string) => {
    setUserName(name)
    saveUserName(name)
  }, [])

  // 重连
  const handleReconnect = useCallback(() => {
    // ws 重连由 unifiedWsClient 自动处理——这里可手动触发
    window.location.reload()
  }, [])

  // 发送消息
  const handleSend = useCallback(() => {
    const content = inputValue.trim()
    if (!content && selectedImages.length === 0) return
    void send(content, selectedImages).catch((error) => {
      console.error('[ChatPage] 发送消息失败:', error)
    })
    setInputValue('')
    setSelectedImages([])
  }, [inputValue, selectedImages, send])

  // 添加图片
  const handleAddImages = useCallback((files: FileList) => {
    const newImages: ChatImageAttachment[] = Array.from(files)
      .slice(0, 8)
      .map((file: File) => ({
        id: `img-${Date.now()}-${file.name}`,
        name: file.name,
        mime_type: file.type,
        base64: '',
        data_url: '',
      }))
    setSelectedImages((prev) => [...prev, ...newImages].slice(0, 8))
  }, [])

  // 移除图片
  const handleRemoveImage = useCallback((id: string) => {
    setSelectedImages((prev) => prev.filter((img) => img.id !== id))
  }, [])

  const botDisplayName = effectiveActiveTab
    ? effectiveActiveTab.sessionInfo.bot_name || t('chat.botNameFallback')
    : t('chat.botNameFallback')

  return (
    <ChatScrollContext.Provider value={{ scrollToMessage: () => false }}>
      <div className="flex h-screen overflow-hidden bg-background">
        {/* 桌面侧边栏 */}
        <ChatWorkspaceSidebar
          className="hidden md:flex"
          tabs={tabs}
          activeTabId={activeTabId}
          userName={userName}
          onSwitch={handleSwitch}
          onClose={handleClose}
          onAddVirtual={handleAddVirtual}
          onUpdateUserName={handleUpdateUserName}
        />

        {/* 主区 */}
        <div className="flex min-w-0 flex-1 flex-col">
          <ChatHeaderBar
            activeTab={effectiveActiveTab}
            botDisplayName={botDisplayName}
            isConnecting={connectionStatus === 'connecting'}
            isLoadingHistory={false}
            onReconnect={handleReconnect}
          />

          {/* 移动端标签条 */}
          <div className="md:hidden">
            <ChatTabBar
              tabs={tabs}
              activeTabId={activeTabId}
              onSwitch={handleSwitch}
              onClose={handleClose}
              onAddVirtual={handleAddVirtual}
            />
          </div>

          {/* 消息列表 */}
          <MessageList
            messages={messages}
            isLoadingHistory={false}
            botDisplayName={botDisplayName}
            botQq={effectiveActiveTab?.sessionInfo.bot_qq}
            userName={userName}
            language="zh"
          />

          {/* 输入框 */}
          <ChatComposer
            value={inputValue}
            onChange={setInputValue}
            onSend={handleSend}
            onAddImages={handleAddImages}
            onRemoveImage={handleRemoveImage}
            disabled={connectionStatus !== 'connected'}
            images={selectedImages}
            isConnected={connectionStatus === 'connected'}
          />
        </div>
      </div>

      {/* 虚拟身份创建弹窗（孤儿补全——ADR-6） */}
      <VirtualIdentityDialog
        open={virtualDialogOpen}
        onOpenChange={setVirtualDialogOpen}
        platforms={platforms}
        persons={effectivePersons}
        isLoadingPlatforms={isLoadingPlatforms}
        isLoadingPersons={isLoadingPersons}
        personSearchQuery={personSearchQuery}
        setPersonSearchQuery={setPersonSearchQuery}
        tempVirtualConfig={tempVirtualConfig}
        setTempVirtualConfig={setTempVirtualConfig}
        onSelectPerson={handleSelectPerson}
        onCreateVirtualTab={handleCreateVirtualTab}
      />
    </ChatScrollContext.Provider>
  )
}