import { Plus, Trash2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { FieldHookComponent } from '@/lib/field-hooks'

import { createJsonFieldHook } from './JsonFieldHookFactory'
import { createListItemEditorHook } from './ListItemEditorHookFactory'

type ExpressionRuleType = 'group' | 'private'

interface ExpressionGroupTarget {
  platform: string
  item_id: string
  rule_type: ExpressionRuleType
}

interface ExpressionGroupValue {
  expression_groups: ExpressionGroupTarget[]
}

const ruleTypeLabel = (rule: unknown) => {
  if (rule === 'private') return '私聊'
  if (rule === 'group') return '群聊'
  return rule ? String(rule) : '未指定'
}

const platformLabel = (item: Record<string, unknown>) => {
  const platform = typeof item.platform === 'string' ? item.platform.trim() : ''
  const itemId = typeof item.item_id === 'string' ? item.item_id.trim() : ''
  if (!platform && !itemId) return '全局'
  if (!platform) return itemId
  if (!itemId) return platform
  return `${platform}:${itemId}`
}

const truncate = (text: string, max = 32) => {
  if (text.length <= max) return text
  return `${text.slice(0, max)}…`
}

const collectStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => (typeof item === 'string' ? item.trim() : ''))
    .filter((item) => item.length > 0)
}

const normalizeExpressionRuleType = (value: unknown): ExpressionRuleType => {
  return value === 'private' ? 'private' : 'group'
}

const normalizeExpressionTarget = (value: unknown): ExpressionGroupTarget => {
  const source =
    value && typeof value === 'object'
      ? (value as Record<string, unknown>)
      : {}
  return {
    platform:
      typeof source.platform === 'string' ? source.platform.trim() : 'qq',
    item_id:
      typeof source.item_id === 'string' ? source.item_id.trim() : '',
    rule_type: normalizeExpressionRuleType(source.rule_type),
  }
}

const normalizeExpressionGroups = (value: unknown): ExpressionGroupValue[] => {
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    const source =
      item && typeof item === 'object'
        ? (item as Record<string, unknown>)
        : {}
    const members = Array.isArray(source.expression_groups)
      ? source.expression_groups.map(normalizeExpressionTarget)
      : []
    return { expression_groups: members }
  })
}

const createExpressionTarget = (): ExpressionGroupTarget => ({
  platform: 'qq',
  item_id: '',
  rule_type: 'group',
})

const formatExpressionTarget = (target: ExpressionGroupTarget): string => {
  const platform = target.platform.trim()
  const itemId = target.item_id.trim()
  const rule = ruleTypeLabel(target.rule_type)
  if (!platform && !itemId) return `全局 · ${rule}`
  if (!itemId) return `${platform} · ${rule}`
  return `${platform}:${itemId} · ${rule}`
}

export const ChatTalkValueRulesHook = createListItemEditorHook({
  addLabel: '添加发言频率规则',
  addButtonPlacement: 'top',
  collapseWhen: ({ parentValues }) => parentValues?.enable_talk_value_rules === false,
  collapsedText: '动态发言频率规则未启用，规则列表已折叠。展开后仍可查看或编辑已有规则。',
  expandLabel: '展开规则',
  collapseLabel: '折叠规则',
  helperText: '可按平台/聊天流/时段分别配置发言频率，留空表示全局。',
  emptyText: '尚未配置任何规则，将使用全局默认频率。',
  fieldRows: [
    ['platform', 'item_id', 'rule_type'],
    ['time', 'value'],
  ],
  itemTitle: (item) => {
    const time =
      typeof item.time === 'string' && item.time.trim()
        ? item.time.trim()
        : '全天'
    const value =
      typeof item.value === 'number' ? item.value.toFixed(2) : '—'
    return `${platformLabel(item)} · ${ruleTypeLabel(item.rule_type)} · ${time} · 频率 ${value}`
  },
})

export const ChatPromptsHook = createListItemEditorHook({
  addLabel: '添加额外 Prompt',
  helperText: '为指定平台和聊天流添加额外提示。platform、item_id 和 prompt 同时留空时表示空条目；填写任意一项后这三项都需要填写。',
  emptyText: '尚未配置任何聊天额外 Prompt。',
  addButtonPlacement: 'top',
  fieldRows: [['platform', 'item_id', 'rule_type']],
  fieldSchemaOverrides: {
    item_id: {
      'x-input-width': '8rem',
      'x-layout': 'inline-right',
    },
    platform: {
      'x-input-width': '8rem',
      'x-layout': 'inline-right',
    },
    prompt: {
      'x-textarea-min-height': 38,
      'x-textarea-rows': 1,
    },
    rule_type: {
      'x-input-width': '8rem',
      'x-layout': 'inline-right',
    },
  },
  iconName: 'file-text',
  itemTitle: (item) => {
    const prompt = typeof item.prompt === 'string' ? item.prompt.trim() : ''
    return `${platformLabel(item)} · ${ruleTypeLabel(item.rule_type)} · ${prompt ? truncate(prompt) : '未填写 Prompt'}`
  },
})

export const ExpressionLearningListHook = createListItemEditorHook({
  addLabel: '添加表达学习规则',
  helperText: '为不同聊天流单独配置是否启用表达/jargon 学习。',
  emptyText: '尚未配置任何学习规则。',
  fieldRows: [
    ['platform', 'item_id', 'rule_type'],
    ['use_expression', 'enable_learning', 'enable_jargon_learning'],
  ],
  itemTitle: (item) => {
    const flags: string[] = []
    if (item.use_expression) flags.push('表达')
    if (item.enable_learning) flags.push('优化学习')
    if (item.enable_jargon_learning) flags.push('jargon')
    const flagText = flags.length ? flags.join(' / ') : '全部关闭'
    return `${platformLabel(item)} · ${ruleTypeLabel(item.rule_type)} · ${flagText}`
  },
})

export const KeywordRulesHook = createListItemEditorHook({
  addLabel: '添加关键词规则',
  helperText: '匹配命中后会用 reaction 内容作为额外上下文。keywords 至少填一条，或使用正则模式。',
  emptyText: '尚未添加任何关键词规则。',
  itemTitle: (item) => {
    const keywords = collectStringList(item.keywords)
    const regex = collectStringList(item.regex)
    const reaction =
      typeof item.reaction === 'string' ? item.reaction.trim() : ''
    const left = keywords.length
      ? `关键词 ${keywords.length} 条`
      : regex.length
        ? `正则 ${regex.length} 条`
        : '未配置匹配项'
    const right = reaction ? `→ ${truncate(reaction)}` : '→ 未填写反应'
    return `${left} ${right}`
  },
})

export const RegexRulesHook = createListItemEditorHook({
  addLabel: '添加正则规则',
  helperText: '正则模式按 Python 语法编写，命中时把 reaction 作为提示注入。',
  emptyText: '尚未添加任何正则规则。',
  itemTitle: (item) => {
    const regex = collectStringList(item.regex)
    const keywords = collectStringList(item.keywords)
    const reaction =
      typeof item.reaction === 'string' ? item.reaction.trim() : ''
    const left = regex.length
      ? `正则 ${regex.length} 条`
      : keywords.length
        ? `关键词 ${keywords.length} 条`
        : '未配置匹配项'
    const right = reaction ? `→ ${truncate(reaction)}` : '→ 未填写反应'
    return `${left} ${right}`
  },
})

export const ExpressionGroupsHook: FieldHookComponent = ({ onChange, value }) => {
  const groups = normalizeExpressionGroups(value)

  const updateGroups = (nextGroups: ExpressionGroupValue[]) => {
    onChange?.(nextGroups)
  }

  const addGroup = () => {
    updateGroups([...groups, { expression_groups: [] }])
  }

  const removeGroup = (groupIndex: number) => {
    updateGroups(groups.filter((_, index) => index !== groupIndex))
  }

  const addMember = (groupIndex: number) => {
    updateGroups(
      groups.map((group, index) =>
        index === groupIndex
          ? {
              expression_groups: [
                ...group.expression_groups,
                createExpressionTarget(),
              ],
            }
          : group
      )
    )
  }

  const removeMember = (groupIndex: number, memberIndex: number) => {
    updateGroups(
      groups.map((group, index) =>
        index === groupIndex
          ? {
              expression_groups: group.expression_groups.filter(
                (_, currentMemberIndex) => currentMemberIndex !== memberIndex
              ),
            }
          : group
      )
    )
  }

  const updateMember = (
    groupIndex: number,
    memberIndex: number,
    patch: Partial<ExpressionGroupTarget>
  ) => {
    updateGroups(
      groups.map((group, index) =>
        index === groupIndex
          ? {
              expression_groups: group.expression_groups.map(
                (member, currentMemberIndex) =>
                  currentMemberIndex === memberIndex
                    ? { ...member, ...patch }
                    : member
              ),
            }
          : group
      )
    )
  }

  return (
    <div className="space-y-4 rounded-lg border bg-card p-4 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h3 className="text-base font-semibold">表达互通组</h3>
          <p className="text-sm text-muted-foreground">
            每个互通组内的聊天流会共享已学习的表达方式。成员会保存为
            expression_groups 数组结构。
          </p>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={addGroup}>
          <Plus className="mr-2 h-4 w-4" />
          添加互通组
        </Button>
      </div>

      {groups.length === 0 ? (
        <div className="rounded-md border border-dashed bg-muted/30 px-4 py-8 text-center text-sm text-muted-foreground">
          暂无互通组，点击“添加互通组”开始配置。
        </div>
      ) : (
        <div className="space-y-3">
          {groups.map((group, groupIndex) => (
            <div
              key={groupIndex}
              className="space-y-3 rounded-md border bg-muted/20 p-3 sm:p-4"
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">
                    互通组 {groupIndex + 1}
                  </span>
                  <Badge variant="secondary">
                    {group.expression_groups.length} 个成员
                  </Badge>
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => addMember(groupIndex)}
                  >
                    <Plus className="mr-2 h-4 w-4" />
                    添加成员
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    aria-label={`删除互通组 ${groupIndex + 1}`}
                    onClick={() => removeGroup(groupIndex)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              {group.expression_groups.length === 0 ? (
                <div className="rounded-md bg-background/70 px-3 py-4 text-sm text-muted-foreground">
                  这个互通组还没有成员。
                </div>
              ) : (
                <div className="space-y-2">
                  {group.expression_groups.map((member, memberIndex) => (
                    <div
                      key={`${groupIndex}-${memberIndex}`}
                      className="grid gap-3 rounded-md bg-background/80 p-3 md:grid-cols-[minmax(7rem,0.75fr)_minmax(10rem,1fr)_minmax(8rem,0.8fr)_auto]"
                    >
                      <div className="space-y-1">
                        <Label className="text-xs">平台</Label>
                        <Input
                          value={member.platform}
                          placeholder="qq"
                          onChange={(event) =>
                            updateMember(groupIndex, memberIndex, {
                              platform: event.target.value,
                            })
                          }
                        />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">账号 / 群号</Label>
                        <Input
                          className="font-mono"
                          value={member.item_id}
                          placeholder="123456"
                          onChange={(event) =>
                            updateMember(groupIndex, memberIndex, {
                              item_id: event.target.value,
                            })
                          }
                        />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">类型</Label>
                        <Select
                          value={member.rule_type}
                          onValueChange={(nextRuleType) =>
                            updateMember(groupIndex, memberIndex, {
                              rule_type: normalizeExpressionRuleType(nextRuleType),
                            })
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="group">群聊</SelectItem>
                            <SelectItem value="private">私聊</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex items-end justify-between gap-2 md:justify-end">
                        <span className="min-w-0 truncate text-xs text-muted-foreground md:hidden">
                          {formatExpressionTarget(member)}
                        </span>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label={`删除互通组 ${groupIndex + 1} 的成员 ${memberIndex + 1}`}
                          onClick={() => removeMember(groupIndex, memberIndex)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {group.expression_groups.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {group.expression_groups.map((member, memberIndex) => (
                    <Badge key={memberIndex} variant="outline">
                      {formatExpressionTarget(member)}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export const MCPRootItemsHook = createJsonFieldHook({
  emptyValue: [],
  helperText: 'MCP Roots 条目为对象数组，使用 JSON 编辑。',
  placeholder: '[\n  {\n    "enabled": true,\n    "uri": "file:///Users/example/project",\n    "name": "project-root"\n  }\n]',
})

export const MCPServersHook = createJsonFieldHook({
  emptyValue: [],
  helperText: 'MCP 服务器配置结构较复杂，使用 JSON 编辑。',
  placeholder: '[\n  {\n    "name": "example-server",\n    "enabled": true,\n    "transport": "stdio",\n    "command": "uvx",\n    "args": ["example-server"],\n    "env": {},\n    "url": "",\n    "headers": {},\n    "http_timeout_seconds": 30.0,\n    "read_timeout_seconds": 300.0,\n    "authorization": {\n      "mode": "none",\n      "bearer_token": ""\n    }\n  }\n]',
})
