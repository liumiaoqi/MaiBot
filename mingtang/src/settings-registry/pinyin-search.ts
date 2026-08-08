import { pinyin } from 'pinyin-pro'

/** 归一化：trim + toLowerCase */
function normalize(s: string): string {
  return s.trim().toLowerCase()
}

/** 获取拼音全拼（无空格） */
function getPinyinFull(text: string): string {
  return pinyin(text, { toneType: 'none', type: 'array' }).join('')
}

/** 获取拼音首字母 */
function getPinyinInitials(text: string): string {
  return pinyin(text, { pattern: 'first', toneType: 'none', type: 'array' }).join('')
}

/** 搜索匹配结果 */
export interface SearchMatchResult {
  matched: boolean
  score: number
}

/** 搜索匹配——子串包含 + 拼音匹配 + 打分 */
export function searchMatch(query: string, keywords: string[]): SearchMatchResult {
  const q = normalize(query)
  if (!q) {
    return { matched: false, score: 0 }
  }

  let bestScore = 0

  for (const kw of keywords) {
    const k = normalize(kw)
    if (!k) continue

    // 精确匹配（100）
    if (q === k) {
      bestScore = Math.max(bestScore, 100)
      continue
    }

    // 前缀匹配（90）
    if (k.startsWith(q)) {
      bestScore = Math.max(bestScore, 90)
      continue
    }

    // 子串匹配（70）
    if (k.includes(q)) {
      bestScore = Math.max(bestScore, 70)
      continue
    }

    // 拼音全拼匹配（50）
    const pinyinFull = getPinyinFull(k)
    if (pinyinFull.includes(q)) {
      bestScore = Math.max(bestScore, 50)
      continue
    }

    // 拼音首字母匹配（40）
    const pinyinInitials = getPinyinInitials(k)
    if (pinyinInitials.includes(q)) {
      bestScore = Math.max(bestScore, 40)
      continue
    }
  }

  return { matched: bestScore > 0, score: bestScore }
}

/** 获取搜索得分——title 命中 +20 加成 */
export function getSearchScore(
  title: string,
  keywords: string[],
  query: string
): SearchMatchResult {
  const kwResult = searchMatch(query, keywords)
  const titleResult = searchMatch(query, [title])

  if (!kwResult.matched && !titleResult.matched) {
    return { matched: false, score: 0 }
  }

  // title 命中 +20 加成
  const score = kwResult.score + (titleResult.matched ? 20 : 0)
  return { matched: true, score }
}