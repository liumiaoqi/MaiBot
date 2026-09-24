import { beforeEach, describe, expect, it, vi } from 'vitest'

import { chatWsClient } from '../chat-ws-client'
import { unifiedWsClient } from '../unified-ws'

vi.mock('../unified-ws', () => ({
  unifiedWsClient: {
    addEventListener: vi.fn(),
    call: vi.fn(),
    closeSession: vi.fn(),
    getStatus: vi.fn(() => 'connected'),
    onConnectionChange: vi.fn(),
    onReconnect: vi.fn(),
    onStatusChange: vi.fn(),
    restart: vi.fn(),
  },
}))

describe('chatWsClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('sends image payloads through message.send', async () => {
    const callMock = vi.mocked(unifiedWsClient.call)
    callMock.mockResolvedValue({})

    await chatWsClient.sendMessage('tab-1', '看看这张图', 'Alice', {
      images: [
        {
          name: 'cat.png',
          mime_type: 'image/png',
          base64: 'iVBORw0KGgo=',
        },
      ],
    })

    expect(callMock).toHaveBeenCalledWith({
      domain: 'chat',
      method: 'message.send',
      session: 'tab-1',
      data: {
        content: '看看这张图',
        images: [
          {
            name: 'cat.png',
            mime_type: 'image/png',
            base64: 'iVBORw0KGgo=',
          },
        ],
        user_name: 'Alice',
      },
    })
  })
})
