import { menuSections } from './constants'
import type { MenuSection } from './types'

/**
 * 侧边栏菜单分组（按需隐藏空分组）。
 *
 * ⚠️ 修 build 记录（2026-10-16，`dashboard-build`）：本文件曾有一套"按功能开关过滤菜单项"的机制
 * ——`interface MenuFeatureFlags { behaviorLearning: boolean }`、`resolveMenuFeatureFlags()`、
 * 以及订阅 `BOT_CONFIG_UPDATED_EVENT` + `getBotConfigCached()` 的那段 effect——它决定是否显示
 * 行为学习相关菜单（`item.featureFlag === 'behaviorLearning'`）。
 *
 * 该功能已于 `933a73344`（"行为学习系统激进档废弃"，2026-07-31，用户裁决 D-01~D-05）**整体移除**：
 * 该提交删掉了上面那个 interface、删掉了唯一消费 flags 的判定行、也删掉了 `MenuSection` 上的
 * `featureFlag` 字段——**但漏删了参数、state、effect 与订阅**。于是 `tsc` 报
 * TS2304（`MenuFeatureFlags` 找不到，因为它被有意删掉了）+ TS6133（`flags` / `item` 参数不再被读）。
 *
 * **修法是"把这次移除做完"，不是补一个新类型**：补类型等于给一个已经不存在的机制留接口，
 * 而 `MenuFeatureFlags` 的"真源"就是被删掉的那个 interface——它不属于别处，也没有被改名。
 * 同理，`constants.ts` 里那个只剩 `{ icon: BehaviorIcon }` 的菜单项也是同一提交的漏删残骸
 * （它的 `label`/`path`/`searchDescription`/`featureFlag` 四行被删了，页面 `/resource/behavior`
 * 与 i18n key `sidebar.menu.behaviorLearning` 都已不存在）——给它补 `label`/`path` 只会造出一个
 * 指向已删页面的坏链接，故一并删除。
 *
 * 若将来要恢复"按开关过滤菜单"，请**连功能本身一起重做**（含 page/route/i18n/key），别只补类型。
 */
export function useMenuSections(): MenuSection[] {
  return menuSections.filter((section) => section.items.length > 0)
}
