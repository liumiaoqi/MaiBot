/**
 * anonymize 昵称抹除体系测试（R3-3-1 测试先行——REQ-R3-13 安全性核心）
 */
import { describe, expect, it, vi } from 'vitest'

import {
  collectMessageTagNicknames,
  collectNicknameCandidates,
  downloadJsonFile,
  eraseNicknames,
  eraseNicknamesFromText,
  eraseReasoningNicknames,
  escapeRegExp,
  formatAnonymousUserName,
  getAnonymousUserName,
  sanitizeDownloadFilename,
} from '../utils/anonymize'

describe('formatAnonymousUserName', () => {
  it('索引 0 → 用户A', () => {
    expect(formatAnonymousUserName(0)).toBe('用户A')
  })

  it('索引 25 → 用户Z', () => {
    expect(formatAnonymousUserName(25)).toBe('用户Z')
  })

  it('索引 26 → 用户AA', () => {
    expect(formatAnonymousUserName(26)).toBe('用户AA')
  })

  it('索引 27 → 用户AB', () => {
    expect(formatAnonymousUserName(27)).toBe('用户AB')
  })

  it('索引 51 → 用户AZ', () => {
    expect(formatAnonymousUserName(51)).toBe('用户AZ')
  })

  it('索引 52 → 用户BA', () => {
    expect(formatAnonymousUserName(52)).toBe('用户BA')
  })
})

describe('getAnonymousUserName', () => {
  it('相同 rawName 返回相同匿名名', () => {
    const nameMap = new Map<string, string>()
    const first = getAnonymousUserName('张三', nameMap)
    const second = getAnonymousUserName('张三', nameMap)
    expect(first).toBe(second)
    expect(nameMap.size).toBe(1)
  })

  it('不同 rawName 返回不同匿名名', () => {
    const nameMap = new Map<string, string>()
    const first = getAnonymousUserName('张三', nameMap)
    const second = getAnonymousUserName('李四', nameMap)
    expect(first).not.toBe(second)
    expect(nameMap.size).toBe(2)
  })

  it('preferredName 优先使用', () => {
    const nameMap = new Map<string, string>()
    const result = getAnonymousUserName('张三', nameMap, '自定义名称')
    expect(result).toBe('自定义名称')
  })

  it('null/undefined rawName 归一为空字符串键', () => {
    const nameMap = new Map<string, string>()
    const result = getAnonymousUserName(null, nameMap)
    expect(result).toBe('用户A')
    expect(nameMap.get('')).toBe('用户A')
  })
})

describe('collectMessageTagNicknames', () => {
  it('从 <message user="张三"> 提取昵称', () => {
    const nameMap = new Map<string, string>()
    collectMessageTagNicknames('<message user="张三" time="12:00">你好</message>', nameMap)
    expect(nameMap.has('张三')).toBe(true)
  })

  it('从 group_card 提取并以 user 为 preferredName', () => {
    const nameMap = new Map<string, string>()
    collectMessageTagNicknames('<message user="张三" group_card="张三的群名片">你好</message>', nameMap)
    expect(nameMap.get('张三')).toBe('用户A')
    expect(nameMap.get('张三的群名片')).toBe('用户A')
  })

  it('多个 message 标签均提取', () => {
    const nameMap = new Map<string, string>()
    collectMessageTagNicknames(
      '<message user="张三">A</message><message user="李四">B</message>',
      nameMap
    )
    expect(nameMap.size).toBe(2)
    expect(nameMap.has('张三')).toBe(true)
    expect(nameMap.has('李四')).toBe(true)
  })

  it('无 message 标签时不收集', () => {
    const nameMap = new Map<string, string>()
    collectMessageTagNicknames('普通文本无标签', nameMap)
    expect(nameMap.size).toBe(0)
  })
})

describe('collectNicknameCandidates', () => {
  it('递归收集对象中的 user_name/display_name/session_display_name/user 字段', () => {
    const nameMap = new Map<string, string>()
    collectNicknameCandidates({
      user_name: '张三',
      nested: { display_name: '李四' },
      list: [{ session_display_name: '王五' }],
    }, nameMap)
    expect(nameMap.has('张三')).toBe(true)
    expect(nameMap.has('李四')).toBe(true)
    expect(nameMap.has('王五')).toBe(true)
  })

  it('字符串值触发 collectMessageTagNicknames', () => {
    const nameMap = new Map<string, string>()
    collectNicknameCandidates('<message user="赵六">文本</message>', nameMap)
    expect(nameMap.has('赵六')).toBe(true)
  })

  it('数组递归收集', () => {
    const nameMap = new Map<string, string>()
    collectNicknameCandidates([
      { user_name: '张三' },
      { user_name: '李四' },
    ], nameMap)
    expect(nameMap.size).toBe(2)
  })

  it('原始值不收集', () => {
    const nameMap = new Map<string, string>()
    collectNicknameCandidates(42, nameMap)
    collectNicknameCandidates(null, nameMap)
    collectNicknameCandidates(undefined, nameMap)
    expect(nameMap.size).toBe(0)
  })
})

describe('escapeRegExp', () => {
  it('转义正则特殊字符', () => {
    expect(escapeRegExp('a.b*c+d?e^f$g{h}i(j)j|k[l]m\\n')).toBe(
      'a\\.b\\*c\\+d\\?e\\^f\\$g\\{h\\}i\\(j\\)j\\|k\\[l\\]m\\\\n'
    )
  })

  it('普通字符串不变', () => {
    expect(escapeRegExp('abc123')).toBe('abc123')
  })
})

describe('eraseNicknamesFromText', () => {
  it('替换文本中的昵称为匿名名', () => {
    const nameMap = new Map<string, string>([['张三', '用户A']])
    expect(eraseNicknamesFromText('张三对李四说', nameMap)).toBe('用户A对李四说')
  })

  it('长名优先替换（避免短名子串误匹配）', () => {
    const nameMap = new Map<string, string>([
      ['张', '用户A'],
      ['张三', '用户B'],
    ])
    expect(eraseNicknamesFromText('张三来了', nameMap)).toBe('用户B来了')
  })

  it('空名跳过', () => {
    const nameMap = new Map<string, string>([['', '用户A']])
    expect(eraseNicknamesFromText('文本', nameMap)).toBe('文本')
  })
})

describe('eraseNicknames', () => {
  it('递归替换对象中的字符串', () => {
    const nameMap = new Map<string, string>([['张三', '用户A']])
    const result = eraseNicknames({ name: '张三', nested: { text: '张三你好' } }, nameMap)
    expect(result).toEqual({ name: '用户A', nested: { text: '用户A你好' } })
  })

  it('数组递归替换', () => {
    const nameMap = new Map<string, string>([['张三', '用户A']])
    const result = eraseNicknames(['张三', '李四', '张三'], nameMap)
    expect(result).toEqual(['用户A', '李四', '用户A'])
  })

  it('原始值不变', () => {
    const nameMap = new Map<string, string>([['张三', '用户A']])
    expect(eraseNicknames(42, nameMap)).toBe(42)
    expect(eraseNicknames(null, nameMap)).toBe(null)
  })
})

describe('eraseReasoningNicknames', () => {
  it('端到端：收集+替换昵称', () => {
    const data = {
      messages: [
        { role: 'user', content: '<message user="张三">你好麦麦</message>' },
        { role: 'assistant', content: '张三你好' },
      ],
      user_name: '张三',
    }
    const result = eraseReasoningNicknames(data) as Record<string, unknown>
    const messages = result.messages as Array<Record<string, unknown>>
    expect(messages[0].content).not.toContain('张三')
    expect(messages[1].content).not.toContain('张三')
    expect(result.user_name).not.toBe('张三')
  })

  it('无昵称时原样返回', () => {
    const data = { text: '无昵称文本', number: 42 }
    const result = eraseReasoningNicknames(data)
    expect(result).toEqual(data)
  })
})

describe('sanitizeDownloadFilename', () => {
  it('清理 Windows 非法字符', () => {
    expect(sanitizeDownloadFilename('a\\b/c:d*e?f"g<h>i|j')).toBe('a_b_c_d_e_f_g_h_i_j')
  })

  it('空格转下划线', () => {
    expect(sanitizeDownloadFilename('hello world')).toBe('hello_world')
  })

  it('截断超长文件名', () => {
    const long = 'a'.repeat(200)
    expect(sanitizeDownloadFilename(long).length).toBe(120)
  })

  it('空字符串回退默认名', () => {
    expect(sanitizeDownloadFilename('   ')).toBe('reasoning-process')
  })
})

describe('downloadJsonFile', () => {
  it('触发浏览器下载', () => {
    const originalCreateElement = document.createElement.bind(document)
    const mockLink = {
      href: '',
      download: '',
      click: () => {},
      remove: () => {},
    }
    const mockClick = vi.fn()
    const mockRemove = vi.fn()
    mockLink.click = mockClick
    mockLink.remove = mockRemove
    const spy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') return mockLink as unknown as HTMLAnchorElement
      return originalCreateElement(tag)
    })
    const appendSpy = vi.spyOn(document.body, 'appendChild').mockImplementation(() => mockLink as unknown as HTMLAnchorElement)

    downloadJsonFile('test.json', { key: 'value' })

    expect(spy).toHaveBeenCalledWith('a')
    expect(mockClick).toHaveBeenCalledOnce()
    expect(mockRemove).toHaveBeenCalledOnce()
    expect(appendSpy).toHaveBeenCalledOnce()

    spy.mockRestore()
    appendSpy.mockRestore()
  })
})