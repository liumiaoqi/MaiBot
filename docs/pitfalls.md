# 踩坑库（实战 26 条）

> 由 `.claude/CLAUDE.md`（2026-10-15 退役）迁入——**修 bug / 写代码前必扫**。
> 配套：`AGENTS.md §七`（高频缺陷模式 12 条·审查对照）· `.shared/postmortem/`（深度复盘·事故级）。

---

1. **模块级实例化** — `emoji_manager.py` 等文件在 import 时创建 LLMOrchestrator，此时 ModelConfigPort 尚未注入
2. **`from ... import __init__` 不可用** — `__init__` 是 Python 特殊属性
3. **`@dataclass` 容易丢失** — 编辑类定义时注意保留装饰器
4. **ThinkAction vs SilenceReason** — `INTENTIONAL` 是 SilenceReason 枚举值，action=SILENT + silence_reason=INTENTIONAL 才是"深思熟虑后不回"
5. **Python 的 `field()` 无 @dataclass 时只是类型注解**，不会生成 __init__
6. **不要本地镜像类型** — 在 A_memorix 内创建核心类型的副本注定不同步，正确方案是下放到 common 层
7. **merge 必须在主仓库执行** — worktree 内 `git merge` 会 "Already up to date"（merge 的是自己分支，新提交永远合不进来）。犯过 3 次。惯例：`cd /mnt/e/Users/lmq/MaiBot && git merge <branch>`，合并前先 `git worktree list` 确认 cwd 不在 worktree 里
8. **worktree 删除后 shell cwd 会失效** — `git worktree remove` 后当前 shell 若还在该目录，后续 git 命令可能落到错误仓库；删 worktree 前先 `cd` 回主仓库
9. **删除/重构模块必须同步测试** — 测试债务主源（2026-08-02 测试卫生批次根因）：删模块后 behavior_* 测试残留、`_chat_manager` 删除后 monkeypatch 字符串目标失效、`chat_prompts` 移入 `reply_style` 后 setattr 目标没跟、f63ca9bf1 删 monologue 漏 bootstrap.py import（启动路径 ImportError）。规则：**删/改任何模块时，grep 其 import 引用 + monkeypatch 字符串引用（"src.x.y" 形式），同步更新或删除测试**；explore agent 核查"零引用"必须含 import 语句级检查
10. **.py 文件必须 UTF-8 无 BOM** — Windows 编辑器保存事故：tests/webui/__init__.py 变 UTF-16 导致整个目录无法收集（SyntaxError: null bytes）。提交前 `file xxx.py` 抽查；跨平台编辑后留意编码
11. **pytests/ 与 tests/ 双目录并存** — 同模块名（webui.conftest）引发 ImportPathMismatchError；已配 `import-mode = "importlib"`（pyproject），不要再手动删其中一个目录，两目录内容不同都有用
12. **faiss≥1.13 裸 IndexHNSWFlat 不支持 add_with_ids** — C++ 基类默认抛 "add_with_ids not implemented"；必须 `faiss.IndexIDMap2(IndexHNSWFlat(...))` 包装（hnsw 参数先设再包）。裸索引 + add_with_ids 的 VectorStore 生产 save() 必崩（2026-08-03 B 类 T3 发现）
13. **sqlite3 连接"拥有权"决定 commit 语义** — 跨连接操作：`conn is self._conn` 时不 commit（参与调用方事务），外部连接要显式 commit（独立生效）。`fts_upsert/delete_tokenized_paragraph` 的 conn 参数曾被实现丢弃 + 自连自提交（破坏 sparse_bm25 独立连接的 shadow 写入，也破坏外层事务）；commit 方向写反过一次（owns_conn 判断反了）
14. **同名方法 v1/v2 并存是空操作陷阱** — `dual_vector_migration.py` 的 `clear_legacy_single_vector_files_after_dual_ready`（v1）只刷 manifest 不删文件，`_v2` 才是真清理——kernel 注入调 v1 → legacy 文件永不清理（"三池冗余"）。规则：grep 同名方法时检查全部定义；删死方法不留双轨
15. **容器内 src 是 bind mount、tests/pytests 不是** — 改 src 立即生效；tests/pytests 在容器里是旧快照（镜像 COPY），跑测试前必须 `docker exec maim-bot-core rm -rf /MaiMBot/tests /MaiMBot/pytests && docker cp tests maim-bot-core:/MaiMBot/ && docker cp pytests maim-bot-core:/MaiMBot/`。忘了同步会把旧测试文件 + 新 src 混跑，报出幽灵失败（2026-08-03 撞过：容器里多了本地已删的 test_maibot_migration_script.py）
16. **str(None) 陷阱（已 5 次）** — `str(x.get("k")).strip()` 对缺 key 返回 `"None"`（非空）导致判空条件永不触发：`_read_manifest_plugin_id` 回填条件永不触发（第 4 次，manifest id）；`_validate_import_chat_id` 无 chat_id 的导入请求全部 400"聊天流不存在: None"（第 5 次，2026-08-04 memory.py，生产 bug）。**规则：`str(x.get("k") or "").strip()`**——审查/写代码时见到 `str(...get(...))` 模式直接警惕
17. **Windows worktree 在 WSL 里 gitdir 失效** — CA 的 Windows 工作树（E:\Users\lmq\MaiBot-fix-send）`.git` 文件内容 `gitdir: E:/...` 是 Windows 绝对路径，WSL 的 git 解析不了 → `git worktree list` 显示 prunable、`git status` 报 "not a git repository: (null)"。修复：`git worktree repair /mnt/e/Users/lmq/MaiBot-fix-send`（2026-08-03 fix_send_failure 合并时撞过）
18. **CA 在子仓库里建嵌套 git 仓库是事故** — CA 的产出目录里若出现带 .git 的子目录（旧副本），`git add` 会作为 gitlink（mode 160000）提交并警告 "adding embedded git repository"——嵌套仓库内容无法被外层仓库管理。规则：合并 CA 产出前先 `find <dir> -name .git` 检查嵌套仓库；内容为旧副本时整个删除，gitlink 从 index 撤销（`git rm --cached`）
19. **submodule 改动两段式提交** — 插件子仓库（plugins/*）的改动必须在子仓库内单独 commit，主仓库只提交指针更新（子仓库 commit → 主仓库 `git add plugins/xxx` 提交指针）
20. **Dummy/假类方法不全 = 错误被吞**（测试卫生批次） — fixture 的 DummyLogger 缺 `debug`/`exception` 方法 → 生产代码调 `logger.debug` 抛 AttributeError → 被外层 try/except 吞 → 断言拿到空字符串、错误不可见。规则：修"断言空结果"类失败时，先检查假类方法是否齐全（logger 至少 debug/info/warning/error/exception），再追链路
21. **fixture 的 sys.modules 假模块替换有时序要求** — 需要 import 真实依赖链的代码（如 port registry 模块）必须在 sys.modules 替换**之前** import；`importlib.reload` 与 sys.modules 假模块互斥（reload 重新 exec 会从被替换模块 import → "cannot import name X from '<unknown module name>'"）。规则：新 import 放 fixture 顶部、不要 reload
22. **Codex 修复可能是"规避"而非"根因"** — 审查 Codex 补丁时对每个生产改动问"它真的修对了吗"：i18n 缺 `import logging`（NameError 根因）被 Codex 用字符串 `"warning"` 规避（破坏 `logger.log(level: int)` 契约）——正确修法是补 import + 走项目 logger 规则。规则：Codex 改了生产代码的语义（参数类型/契约）时重点审查；宁可还原其改动自己修
23. **真实 db 的测试残留要测试内清理** — 走真实 db（AgentActivityStore 等）的测试重跑会 UNIQUE 冲突/数据累积——测试开头 delete 同 id 记录，或改用临时 db 隔离。数据库迁移只跑一次：已跑过新版本的测试环境，后续补列要手动 ALTER（迁移文件对新 db 生效，旧 db 已跳版本）
24. **HTTPS 调用失败排查分叉** — httpx/requests 自带 certifi（捆绑 CA）不受系统影响；标准库 urllib 只用系统 CA（Python 查 /usr/lib/ssl/cert.pem，非 /etc/ssl/certs/）——容器精简镜像（--no-install-recommends）可能既没 ca-certificates 包也没有 /usr/lib/ssl 目录，导致只有 urllib 路径挂（2026-08-04 avatar 头像路由 SSL CERTIFICATE_VERIFY_FAILED，其他 LLM 调用正常）。规则：① 排查"某个 HTTPS 调用失败其他正常"先想到这个分叉 ② Dockerfile 必须装 ca-certificates ③ 容器即时修复：宿主机 `cat /etc/ssl/certs/ca-certificates.crt | docker exec -i <容器> tee /usr/lib/ssl/cert.pem`
25. **uuid7().hex[:8] 截断 = 时间戳前缀碰撞（TG-9 回归第 2 次）** — uuid7 前 8 个 hex 字符是毫秒时间戳高 32 位（~65.5s 才变一次），同进程背靠背生成必然相同；截断 `hex[:8]` 丢掉了随机低位。2026-07-28 TG-9 把传输实例 ID 从 uuid4 改 uuid7 截断 → 双 Supervisor 同 socket 地址 → UDS 无条件 unlink 抢占 → Runner 交叉连接被拒（退出码 0）。规则：① uuid7 只用于**持久化主键**（完整值）；**临时/ephemeral 实例 ID 用 uuid4** ② 任何 `uuid*.hex[:N]` 截断都要想"截的是随机位还是时间位" ③ 排查"稳定复现的启动失败"先查 ID 生成
26. **容器内对 bind mount 目录 rm/docker cp 会穿透破坏宿主机文件**（2026-08-05 ZG-12 批 2 事故）— 容器内 `rm -rf /MaiMBot/src` 递归删除宿主机 src（bind mount 穿透），`docker cp src → /MaiMBot/src` 覆盖挂载点内容；后续 `git restore src/` 又把未提交的批 2 修改（T11-T17 全部）无差别还原成 HEAD——**两层事故**。规则：① **bind mount 目录（src/prompts/agents/lab）禁止容器内 rm/cp 操作**——宿主机改文件即时生效，容器内只读 ② 恢复被删文件用 `git restore src/ -- <具体文件>`（只恢复删除的），**绝不无差别 `git restore <dir>`** ③ 验证基线用 `git stash` 后注意容器 src 同步：stash 期间容器内 src 是旧版，恢复后 `docker compose restart` 重新挂载（bind mount 无需 cp）④ 事故恢复优先顺序：git 恢复 → 会话记录重写（所有 Edit/Write 内容都在对话里）

---

## 追加（2026-08 下旬批次）

27. **"开关+列表"两层配置，开关没开列表就是摆设**（2026-08-07 事故）— napcat 适配器 `enable_chat_list_filter = false` + `group_list = []`：过滤开关没开 → 白名单列表完全不生效 → **MaiBot 在未配置的群里主动发言刷屏**（用户"没配置白名单"的直觉 = 实际"全部放行"，默认值是最危险的配置）。规则：① 检查"白名单/过滤"类配置必须同时看**开关和列表**两层 ② 安全默认值应取"全禁"再逐步放行 ③ 遇"没配置=放行"语义的配置，改配置时先确认意图 ④ 止损：开过滤开关 + 空列表 = 群聊全禁私聊照常
28. **.dockerignore/.gitignore 必须 LF 换行，CRLF 会让 buildkit 静默忽略全部排除规则**（2026-08-07 镜像体积事故）— Windows 创建的 .dockerignore 是 CRLF——buildkit 解析时行尾 `\r` 污染模式匹配，**所有排除静默失效**（不报错）：.git（4GB）+ data（857MB）+ lab（150MB）全被 COPY 进镜像 → COPY 层 7.38GB、镜像 14.3GB（正常应 2-3GB）。规则：① 编辑后 `file` 检查换行（"with CRLF line terminators" = 有问题）② 修复 `tr -d '\r' < file > tmp && mv tmp file` ③ 排查镜像异常大：`docker history <img> --format "{{.Size}}\t{{.CreatedBy}}"` ④ docker-desktop 发行版 /mnt/e 挂载可能陈旧——查 daemon 侧文件用 `wsl.exe -d docker-desktop -- ls /mnt/e/...`
29. **.codeartsdoer 目录 gitignore 需 `-f` 强制添加** — `.codeartsdoer/` 有独立 ignore 规则（specs 等不入主仓库 git），`git add .codeartsdoer/xxx` 会静默跳过——需 `git add -f`。规则：add 后 `git status` 确认实际进 index
30. **"全量 pytest"必须真的全量**（2026-08-08 明堂-1 教训）— CA 自审声称"全量 pytest 57 passed"，实际只跑了 `tests/webui` 局部——真全量（tests + pytests，1956 collected）是 1860 passed / 11 failed / 32 errors——**pytests/webui 32 errors 因此被漏**。规则：① 验收声明"全量"时对照 `pytest --collect-only` 总数（1956 量级）② 局部跑只能称"局部" ③ 重构模块后必须 grep 全部 `"src.x.y"` monkeypatch 字符串引用并同步 ④ 双目录并存时 `tests/` 与 `pytests/` 根目录都需 `__init__.py`
31. **docker-desktop 内 /mnt/e symlink 退化 = 容器全挂**（2026-08-09 事故）— E 盘（移动硬盘）掉盘后，docker-desktop 发行版里 `/mnt/e` 的 symlink（正常指向 /mnt/host/e）**退化成空目录**；容器 bind mount 解析到空目录 → "not a directory" → maim-bot-core 起不来 → 前端全部 API 400/500。主发行版掉盘后能自愈，docker-desktop **不自愈**。规则：① 信号：WSL 里 /mnt/e I/O 错误 = 掉盘先兆 ② 修复：`wsl -d docker-desktop -- sh -c "rm -rf /mnt/e && ln -s /mnt/host/e /mnt/e"` 后 `docker start maim-bot-core` ③ 预防：禁用 USB 选择性暂停/硬盘休眠；根治 = 换内置盘 ④ 查 daemon 侧文件用 `wsl.exe -d docker-desktop -- ls /mnt/host/e/...`
32. **主题/视觉问题四大类根因**（2026-08-09 主题验收轮）：
    - a) **批量正则改 className 属性错位**：`<h3 className="X" text-foreground>`——类插到引号**外**成无效属性（13 处——config 域全部标题黑字"修完还在"的根因）。规则：批量改 className 后 grep 验证 `className="[^"]*" (text-|bg-)` 模式零残留
    - b) **注入变量零消费端**：`--retro-*` 注入了但**没有任何样式 var() 消费**——设置"没效果"的根因。规则：加注入变量必须同时加消费端——grep `var(--xxx)` 验证
    - c) **React 闭包竞态**（快速连点触发）：`updateThemeConfig` 闭包捕获 `resolvedTheme`——连点时闭包过期 → 明暗随机跳变。规则：**依赖 state 的计算用权威源实时计算**（localStorage 同步写 + matchMedia 实时查询）而非闭包/ref；写**连点压力测试**（交替快速点击 10 次——断言最终明暗与权威源一致）
    - d) **背景图被盖**：纹理背景加在 html——被 Layout 根 div 的不透明背景盖住。规则：背景图加在**最顶层背景元素**（shell——data-dashboard-shell）而非 html
    - 配套检测机制：连点压力测试 / 注入-消费配对 grep / className 错位 grep / E2E（Playwright——视觉盲区 jsdom 测不了）
