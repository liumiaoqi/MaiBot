import { isRecord } from './format'
import { parseMessageTagAttributes } from './tag-parse'

export function formatAnonymousUserName(index: number): string {
  let value = index
  let suffix = ''
  do {
    suffix = String.fromCharCode(65 + (value % 26)) + suffix
    value = Math.floor(value / 26) - 1
  } while (value >= 0)
  return `用户${suffix}`
}

export function getAnonymousUserName(rawName: unknown, nameMap: Map<string, string>, preferredName?: string): string {
  const nameKey = String(rawName ?? '')
  const existingName = nameMap.get(nameKey)
  if (existingName) return existingName

  const anonymousName = preferredName ?? formatAnonymousUserName(new Set(nameMap.values()).size)
  nameMap.set(nameKey, anonymousName)
  return anonymousName
}

export function collectMessageTagNicknames(text: string, nameMap: Map<string, string>): void {
  const messageTagPattern = /<message\b([^>]*)>/gi
  for (const match of text.matchAll(messageTagPattern)) {
    const attrs = parseMessageTagAttributes(match[1] ?? '')
    const userName = attrs.user ? getAnonymousUserName(attrs.user, nameMap) : undefined
    if (attrs.group_card) {
      getAnonymousUserName(attrs.group_card, nameMap, userName)
    }
  }
}

export function collectNicknameCandidates(value: unknown, nameMap: Map<string, string>): void {
  if (Array.isArray(value)) {
    value.forEach((item) => collectNicknameCandidates(item, nameMap))
    return
  }
  if (typeof value === 'string') {
    collectMessageTagNicknames(value, nameMap)
    return
  }
  if (!isRecord(value)) return

  const userName = typeof value.user === 'string' ? getAnonymousUserName(value.user, nameMap) : undefined
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === 'string') {
      if (key === 'user_name' || key === 'display_name' || key === 'session_display_name' || key === 'user') {
        getAnonymousUserName(item, nameMap)
      } else if (key === 'group_card') {
        getAnonymousUserName(item, nameMap, userName)
      }
    }
    collectNicknameCandidates(item, nameMap)
  }
}

export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function eraseNicknamesFromText(text: string, nameMap: Map<string, string>): string {
  return Array.from(nameMap.entries())
    .filter(([name]) => name.length > 0)
    .sort(([left], [right]) => right.length - left.length)
    .reduce((current, [name, anonymousName]) => current.replace(new RegExp(escapeRegExp(name), 'g'), anonymousName), text)
}

export function eraseNicknames(value: unknown, nameMap = new Map<string, string>()): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => eraseNicknames(item, nameMap))
  }
  if (typeof value === 'string') {
    return eraseNicknamesFromText(value, nameMap)
  }
  if (!isRecord(value)) return value

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [key, eraseNicknames(item, nameMap)])
  )
}

export function eraseReasoningNicknames(value: unknown): unknown {
  const nameMap = new Map<string, string>()
  collectNicknameCandidates(value, nameMap)
  return eraseNicknames(value, nameMap)
}

export function sanitizeDownloadFilename(value: string): string {
  return value
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '_')
    .replace(/\s+/g, '_')
    .slice(0, 120) || 'reasoning-process'
}

export function downloadJsonFile(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}