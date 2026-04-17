import { unifiedWsClient, type ConnectionStatus } from './unified-ws'

interface ChatSessionOpenPayload {
  group_id?: string
  group_name?: string
  person_id?: string
  platform?: string
  user_id?: string
  user_name?: string
}

type ChatSessionListener = (message: Record<string, unknown>) => void

class ChatWsClient {
  private initialized = false
  private listeners: Map<string, Set<ChatSessionListener>> = new Map()
  private sessionPayloads: Map<string, ChatSessionOpenPayload> = new Map()

  private initialize(): void {
    if (this.initialized) {
      return
    }

    unifiedWsClient.addEventListener((message) => {
      if (message.domain !== 'chat' || !message.session) {
        return
      }

      const sessionListeners = this.listeners.get(message.session)
      if (!sessionListeners) {
        return
      }

      sessionListeners.forEach((listener) => {
        try {
          listener(message.data)
        } catch (error) {
          console.error('聊天会话监听器执行失败:', error)
        }
      })
    })

    unifiedWsClient.onReconnect(() => {
      void this.reopenSessions()
    })

    this.initialized = true
  }

  private async reopenSessions(): Promise<void> {
    const reopenTargets = Array.from(this.sessionPayloads.entries())
    for (const [sessionId, payload] of reopenTargets) {
      try {
        await unifiedWsClient.call({
          domain: 'chat',
          method: 'session.open',
          session: sessionId,
          data: {
            ...payload,
            restore: true,
          } as Record<string, unknown>,
        })
      } catch (error) {
        console.error(`恢复聊天会话失败 (${sessionId}):`, error)
      }
    }
  }

  async openSession(sessionId: string, payload: ChatSessionOpenPayload): Promise<void> {
    this.initialize()
    this.sessionPayloads.set(sessionId, payload)
    await unifiedWsClient.call({
      domain: 'chat',
      method: 'session.open',
      session: sessionId,
      data: payload as Record<string, unknown>,
    })
  }

  async closeSession(sessionId: string): Promise<void> {
    this.sessionPayloads.delete(sessionId)
    if (unifiedWsClient.getStatus() !== 'connected') {
      return
    }

    try {
      await unifiedWsClient.call({
        domain: 'chat',
        method: 'session.close',
        session: sessionId,
        data: {},
      })
    } catch (error) {
      console.warn(`关闭聊天会话失败 (${sessionId}):`, error)
    }
  }

  async sendMessage(sessionId: string, content: string, userName: string): Promise<void> {
    await unifiedWsClient.call({
      domain: 'chat',
      method: 'message.send',
      session: sessionId,
      data: {
        content,
        user_name: userName,
      },
    })
  }

  async updateNickname(sessionId: string, userName: string): Promise<void> {
    const currentPayload = this.sessionPayloads.get(sessionId)
    if (currentPayload) {
      this.sessionPayloads.set(sessionId, {
        ...currentPayload,
        user_name: userName,
      })
    }

    await unifiedWsClient.call({
      domain: 'chat',
      method: 'session.update_nickname',
      session: sessionId,
      data: {
        user_name: userName,
      },
    })
  }

  onSessionMessage(sessionId: string, listener: ChatSessionListener): () => void {
    this.initialize()
    const sessionListeners = this.listeners.get(sessionId) ?? new Set<ChatSessionListener>()
    sessionListeners.add(listener)
    this.listeners.set(sessionId, sessionListeners)

    return () => {
      const currentListeners = this.listeners.get(sessionId)
      if (!currentListeners) {
        return
      }

      currentListeners.delete(listener)
      if (currentListeners.size === 0) {
        this.listeners.delete(sessionId)
      }
    }
  }

  onConnectionChange(listener: (connected: boolean) => void): () => void {
    return unifiedWsClient.onConnectionChange(listener)
  }

  onStatusChange(listener: (status: ConnectionStatus) => void): () => void {
    return unifiedWsClient.onStatusChange(listener)
  }

  async restart(): Promise<void> {
    await unifiedWsClient.restart()
  }
}

export const chatWsClient = new ChatWsClient()
