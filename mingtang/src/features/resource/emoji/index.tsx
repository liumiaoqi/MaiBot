/**
 * 表情精选展示页（R4-1-1-3）
 *
 * 定位：精选展示（15-20 条手动标注 + 描述清单）——非原版全量 CRUD
 * 数据流：静态导入 curatedEmojis（禁止 getEmojiList 全量拉取——spec.md §5.1.1 #8）
 * 三态：加载骨架 → 正常态/空态
 * 禁止：状态切换 Tabs / 搜索 / 筛选 / 排序 / 分页 / 批量删除 / 上传 / 缓存维护 / 注册封禁
 *
 * design.md §2.2.2.1 / ADR-1 精选定位 / ADR-5 主题零黑字
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EmptyState } from '@/components/biz/empty-state'
import { LoadingSkeleton } from '@/components/biz/loading-skeleton'
import { PageShell } from '@/components/biz/page-shell'

import { CuratedEmojiCard } from './components/curated-emoji-card'
import { curatedEmojis, type CuratedEmoji } from './curated-emojis'

type PagePhase = 'loading' | 'empty' | 'success'

interface EmojiCuratedPageProps {
  /** 精选清单数据源（默认静态导入 curatedEmojis——测试可注入） */
  items?: CuratedEmoji[]
}

/**
 * 表情精选展示页主组件
 *
 * 精选清单为静态配置（curated-emojis.ts）——不调 getEmojiList 全量拉取
 * 后续换数据源（静态→后端接口）：改 curatedEmojis 导出方式 + 加 useQuery——组件接口不变
 */
export function EmojiCuratedPage({ items = curatedEmojis }: EmojiCuratedPageProps = {}): React.ReactElement {
  const { t } = useTranslation()
  const [phase, setPhase] = useState<PagePhase>('loading')

  useEffect(() => {
    const timer = setTimeout(() => {
      setPhase(items.length === 0 ? 'empty' : 'success')
    }, 0)
    return () => clearTimeout(timer)
  }, [items])

  return (
    <PageShell
      title={t('resource.emoji.title')}
      breadcrumb={[t('sidebar.categories.resources'), t('resource.emoji.title')]}
    >
      {phase === 'loading' && <LoadingSkeleton rows={6} message={t('resource.emoji.loading')} />}

      {phase === 'empty' && <EmptyState message={t('resource.emoji.empty')} />}

      {phase === 'success' && (
        <div
          className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5"
          data-testid="curated-emoji-grid"
        >
          {items.map((emoji) => (
            <CuratedEmojiCard key={emoji.emoji_id} emoji={emoji} />
          ))}
        </div>
      )}
    </PageShell>
  )
}
