# 启动编排算法方案集

> 2026-07-27，CA 整理
> 目的：记录所有可行方案，等 MaiBot 复杂度增长到能区分算法差异时再择优

## 当前状态

- 组件数：~30
- 启动时间：~1-2s（未精确测量）
- 依赖关系：手工排序，全串行
- 算法差异不可感知：30 个组件串行 vs 并行差距 <100ms

## 方案 A：手工顺序（当前）

```python
steps = [step1, step2, step3, ..., step31]
for step in steps:
    await step.init_fn()
```

- 复杂度：O(n) 串行
- 优点：简单，确定性 100%
- 缺点：加组件要手动找位置，无法并行
- 适用：组件 < 50，启动时间 < 5s

## 方案 B：声明依赖 + 拓扑排序

```python
@component(after=["config"], requires=["database"])
async def init_memorix(): ...

# graphlib.TopologicalSorter 自动排序
# 无依赖的并行启动
```

- 复杂度：O(V+E) 排序 + 并行执行
- 优点：加组件只声明依赖，编排器自动算顺序；无依赖组件并行
- 缺点：要写依赖声明；循环依赖要检测
- 适用：组件 30-100，有并行启动空间
- Python 标准库：`graphlib.TopologicalSorter`（3.9+）

## 方案 C：分层 target（systemd 化）

```python
# 组件挂到 target，target 之间有顺序，target 内并行
target("early",  components=[config, logger, database])
target("core",   components=[ports, orchestrator, memorix], after="early")
target("plugin", components=[v1_runtime, v2_runtime], after="core")
target("late",   components=[webui, scheduler], after="plugin")
```

- 复杂度：O(T) target 排序 + O(C_t) target 内并行
- 优点：比 B 更粗粒度，人类可理解；target 是可达性标记
- 缺点：粒度粗，同 target 内无依赖关系的组件也被绑在一起
- 适用：组件 50-200，需要分阶段启动

## 方案 D：惰性启动（lazy init）

```python
# 组件首次被使用时才初始化
@lazy_component
class AMemorix:
    async def _ensure_initialized(self):
        if not self._ready:
            await self._init()
            self._ready = True

# 首次调用 await memorix.query() 触发 _ensure_initialized
```

- 复杂度：O(1) 启动 + O(k) 首次使用时初始化
- 优点：启动极快；按需初始化省资源
- 缺点：首次使用延迟不可预测；初始化失败时机推迟到运行时
- 适用：组件多但不是启动时都需要；冷启动优化

## 方案 E：自研——自适应编排

> 探索性方案，尝试超越现有 OS 启动算法

**核心思想**：不预先声明依赖，而是**运行时探测**——尝试启动，失败则记录缺依赖，等依赖满足后重试。

```python
async def adaptive_boot(components):
    failed = set()
    started = set()
    pending = set(components)
    
    while pending:
        progress = False
        for comp in list(pending):
            try:
                await comp.start()  # 尝试启动
                started.add(comp)
                pending.remove(comp)
                progress = True
            except DependencyMissing as e:
                # 记录缺什么，不声明，靠运行时发现
                comp.missing_deps = e.deps
                failed.add(comp)
        
        if not progress:
            # 一轮下来没有任何组件成功 → 死锁
            raise BootDeadlock(failed)
        
        # 重新尝试之前失败的（它们的依赖可能已满足）
        pending.update(failed)
        failed.clear()
```

- 复杂度：最坏 O(n²)（每轮只成功一个），平均 O(n·k)（k=重试轮数）
- 优点：**零声明**——不用写依赖，算法自动发现；组件增删不改编排代码
- 缺点：最坏情况差；依赖靠试错发现，不如声明式可靠；启动时间不可预测
- 适用：依赖关系不稳定、组件动态增删的场景
- **与 B 的关系**：B 是编译时声明依赖，E 是运行时发现依赖。E 更灵活但更不可控

## 方案 F：自研——基于类型的依赖推断

> 尝试从组件的函数签名自动推断依赖

```python
class AMemorix:
    async def start(self, config: ConfigPort, database: DatabasePort):
        # 签名里的参数类型就是依赖！
        ...

# 编排器用 inspect.signature 自动提取依赖
deps = {
    AMemorix: {ConfigPort, DatabasePort},
    PluginV2: {AppConfigPort, AMemorix},  # 自动推断
}
```

- 复杂度：O(V+E) 同 B，但依赖声明零成本（从签名推断）
- 优点：不用手写 `after=/requires=`，签名即依赖；重构时依赖自动更新
- 缺点：隐式，人类不可直接看到依赖图；接口类型和实现类型的映射需约定
- 适用：组件接口稳定的系统；Python 类型注解完善的代码库
- **与 B 的关系**：F 是 B 的自动化版本——B 手写依赖，F 从签名推断依赖

## 算法差异何时可感知？

| 指标 | 当前 | 差异阈值 | 说明 |
|------|------|---------|------|
| 组件数 | ~30 | ~50 | 拓扑排序 vs 手工排序的维护成本差异显现 |
| 启动时间 | ~1-2s | ~5s | 并行启动的收益可测量 |
| 并行度 | 0（全串行） | Port 12 个可并行 | 当前 12 个 Port 串行启动，并行可省 ~100ms |
| 组件增删频率 | 低 | 每周 >1 次 | 手工排序的维护成本与频率成正比 |
| 依赖复杂度 | 线性链 | 出现菱形依赖 | A→B, A→C, B→D, C→D 时手工排序易错 |
| 动态组件 | 无 | 运行时加载插件 | 惰性启动（方案 D）价值显现 |

**预测**：当 MaiBot 达到以下任一条件时，方案 B（拓扑排序）明显优于 A：
- 组件 > 50
- 启动时间 > 5s
- 出现菱形依赖
- 插件运行时动态加载

方案 E/F 的价值要等更复杂的场景（动态依赖、组件热插拔）。

## 实验设计

当复杂度到达阈值时，用以下实验比较：

```
实验 1：启动时间
  A(串行) vs B(拓扑+并行) vs C(分层target)
  测量：冷启动时间、热启动时间

实验 2：维护成本
  新增 5 个组件，测量人工修改启动编排的时间
  A：找插入位置 + 调顺序
  B：写依赖声明，编排器自动排

实验 3：鲁棒性
  随机删一个组件的依赖，看哪个方案先报错
  A：运行时崩溃
  B：启动时拓扑排序报循环依赖
  E：运行时重试后报死锁
```