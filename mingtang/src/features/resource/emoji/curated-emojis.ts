/**
 * 精选表情清单数据源（R4-1-1-1）
 *
 * 定位：精选展示（15-20 条手动标注）——非原版全量 CRUD
 * 扩展性：后续加表情只需在 curatedEmojis 数组加项，页面自动展示（无需改组件代码）
 * 认证：缩略图通过 getEmojiThumbnailUrl(emoji_id) 拼接 URL——HttpOnly Cookie 认证（浏览器自动携带）
 *
 * design.md §2.3.2 / ADR-2
 */

/**
 * 精选表情条目（spec.md §6.1——留扩展性）
 */
export interface CuratedEmoji {
  /** 表情标识——关联后端表情记录（缩略图URL拼接/后续详情拉取） */
  emoji_id: number
  /** 描述文本——人工标注（描述清单核心——供角色LLM sticker picker自选） */
  description: string
  /** 情感标签（可选——后续扩展） */
  emotion?: string
  /** 标签列表（可选——后续扩展） */
  tags?: string[]
  /** 分类（可选——后续扩展） */
  category?: string
}

/**
 * 精选清单——15-20 条手动标注（精选定位——非全量）
 *
 * 约束：
 * - 清单规模 15-20 条（spec.md §6.1 #5）
 * - 数据源可配置（静态配置——后续加表情只需在数组加项，不重写页面组件——spec.md §5.1.1 #3）
 * - emoji_id 对应后端表情记录 ID（缩略图通过 getEmojiThumbnailUrl 拼接）
 */
export const curatedEmojis: CuratedEmoji[] = [
  {
    emoji_id: 1,
    description: '开心——嘴角上扬的笑脸，表达喜悦与愉快',
    emotion: 'happy',
    tags: ['正面', '日常'],
    category: '基础情绪',
  },
  {
    emoji_id: 2,
    description: '思考——手托下巴若有所思，表达沉思与琢磨',
    emotion: 'thinking',
    tags: ['中性', '工作'],
    category: '基础情绪',
  },
  {
    emoji_id: 3,
    description: '惊讶——张大嘴巴睁圆双眼，表达出乎意料',
    emotion: 'surprised',
    tags: ['中性', '日常'],
    category: '基础情绪',
  },
  {
    emoji_id: 4,
    description: '委屈——撇嘴低头，表达受委屈与不甘',
    emotion: 'sad',
    tags: ['负面', '日常'],
    category: '基础情绪',
  },
  {
    emoji_id: 5,
    description: '得意——眯眼微笑，表达小得意与满足',
    emotion: 'happy',
    tags: ['正面', '日常'],
    category: '基础情绪',
  },
  {
    emoji_id: 6,
    description: '困惑——挠头疑惑，表达不解与困惑',
    emotion: 'confused',
    tags: ['中性', '日常'],
    category: '基础情绪',
  },
  {
    emoji_id: 7,
    description: '生气——皱眉撅嘴，表达不满与愤怒',
    emotion: 'angry',
    tags: ['负面', '日常'],
    category: '基础情绪',
  },
  {
    emoji_id: 8,
    description: '期待——搓手等待，表达期待与盼望',
    emotion: 'excited',
    tags: ['正面', '日常'],
    category: '基础情绪',
  },
  {
    emoji_id: 9,
    description: '无奈——摊手叹气，表达无可奈何',
    emotion: 'sad',
    tags: ['负面', '日常'],
    category: '基础情绪',
  },
  {
    emoji_id: 10,
    description: '调皮——吐舌眨眼，表达俏皮与玩闹',
    emotion: 'playful',
    tags: ['正面', '日常'],
    category: '基础情绪',
  },
  {
    emoji_id: 11,
    description: '害羞——捂脸低头，表达不好意思与羞涩',
    emotion: 'shy',
    tags: ['中性', '日常'],
    category: '基础情绪',
  },
  {
    emoji_id: 12,
    description: '困倦——打哈欠，表达疲惫与想睡',
    emotion: 'tired',
    tags: ['中性', '日常'],
    category: '基础情绪',
  },
  {
    emoji_id: 13,
    description: '加油——握拳鼓励，表达打气与支持',
    emotion: 'encouraging',
    tags: ['正面', '社交'],
    category: '社交互动',
  },
  {
    emoji_id: 14,
    description: '抱抱——张开双臂，表达安慰与温暖',
    emotion: 'caring',
    tags: ['正面', '社交'],
    category: '社交互动',
  },
  {
    emoji_id: 15,
    description: '点赞——竖起大拇指，表达赞同与认可',
    emotion: 'happy',
    tags: ['正面', '社交'],
    category: '社交互动',
  },
  {
    emoji_id: 16,
    description: '暗中观察——偷瞄窥视，表达好奇与试探',
    emotion: 'curious',
    tags: ['中性', '日常'],
    category: '趣味',
  },
  {
    emoji_id: 17,
    description: '吃瓜——捧瓜围观，表达看热闹与八卦',
    emotion: 'amused',
    tags: ['正面', '社交'],
    category: '趣味',
  },
  {
    emoji_id: 18,
    description: '溜了——转身跑路，表达开溜与回避',
    emotion: 'playful',
    tags: ['中性', '日常'],
    category: '趣味',
  },
] satisfies CuratedEmoji[]