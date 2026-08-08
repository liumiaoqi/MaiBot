import { Fragment, type ReactNode } from 'react'

/** 搜索高亮——匹配区间用 <mark> 包裹（仅子串匹配高亮，拼音不高亮） */
export function highlightMatch(text: string, query: string): ReactNode {
  if (!query || !query.trim()) {
    return text
  }

  const q = query.trim().toLowerCase()
  const lowerText = text.toLowerCase()
  const idx = lowerText.indexOf(q)

  // 子串不匹配 → 不高亮（拼音匹配无法定位原文区间）
  if (idx === -1) {
    return text
  }

  const before = text.slice(0, idx)
  const matched = text.slice(idx, idx + q.length)
  const after = text.slice(idx + q.length)

  return (
    <Fragment>
      {before}
      <mark className="rounded bg-yellow-200/60 px-0.5 text-inherit">{matched}</mark>
      {after}
    </Fragment>
  )
}