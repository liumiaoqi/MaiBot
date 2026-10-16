# 踩坑库（**条数不登记** —— 见 `AGENTS §七`：条数是会腐的登记，2026-10-16 实测三处各写 25/26/32 而实际 33）

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
33. **新 worktree 必缺三类 gitignored/submodule 资源 ⇒ 判据门跑不动（不是"多几个失败"）**（2026-10-16 配置体系轮 · **一轮内撞五次**）— `git worktree add` 只检出**跟踪内容**，而本仓有三类东西天生不在 git 里：① **`config/model_config.toml`**（`.gitignore` 的 `/config/*`）⇒ 缺它 `tests/webui/test_config*.py` 报 **404**；② **`plugins/maibot-team.napcat-adapter` / `plugins/maibot-team.v1-compat`**（**无 URL 的 gitlink**，本仓 `.gitmodules` **不存在** ⇒ `git submodule update` 直接 `error: No url found`）⇒ 缺它**收集期**就 `FileNotFoundError: _manifest.json` / `ModuleNotFoundError: ...message_codec`，**一个用例都跑不了**；③ **`.shared/`**（空壳）⇒ 往 `.shared` 写文件会落进空目录、看不到内容。
    规则：① **建树后立刻补这三类**（从主 checkout 拷；**用 `robocopy /E`**——⚠️ **2026-10-17 实测：`xcopy /E /I /Y /Q` 会静默少拷**：napcat-adapter 只出 **64/260**、v1-compat **13/78**，**而命令不报错**（隐藏文件得加 `/H`）；`Copy-Item` 在目标父目录缺失时也可能静默不成）⇒ **拷完必须核**：`codecs/inbound/message_codec.py` 与 `codecs/outbound/message_codec.py` **两个源码都在** + `maibot-team.v1-compat` 的 `_manifest.json` 在位；② **别用"整文件覆盖"去补"多段都改过"的文件**——会互相抹掉（实测把 3 段的 `ConfigWriteRefusedError` 抹没了，而 `git status` 看着干净）；③ 判据门跑不动时**先查这三类**，别先怀疑自己的改动；④ **还有第四件：`.venv`**——`uv run --no-sync` 遇到空 venv **不报错**，而是**带着缺依赖硬跑**（实测缺 `jieba`/`grpc`/`watchfiles`/`json_repair` ⇒ **154 个收集错误**、收集总数从 4918 掉到 3405）；建树后跑一次 **`uv sync --frozen`**；⑤ 自检命令**必须带目录参数**：`pytest tests pytests --collect-only -q | tail -1` 应显示 ~4918（**裸 `pytest` 会爬 `scripts/embedding_finetune` 实验区**，同样报一堆假错），**不是** `Interrupted: N errors during collection`。
    ⚠️ **主 checkout 同样中招（2026-10-17 实测补）**：裸 `uv run pytest` 在**主仓**除 `scripts/embedding_finetune/` 外还收 **`temp/` 3 个**（`test_config.py` / `test_inner_world.py` / `test_integration.py`）⇒ **5 个** collection ERROR **中止整轮**（主仓 `addopts` 只 ignore `lab`）⇒ **验收口径固定 `tests pytests`**（本条不是"worktree 专属"）。
    备注（2026-10-17，同夜实测两条）：① **核资源别只看文件数**——`__pycache__` 会涨（某树 60/16 **超过**主仓 36/8）、重复拷贝会**嵌套**（同一棵树里 `plugins/maibot-team.napcat-adapter/maibot-team.napcat-adapter/…` 再来一层）、只缺 `.pyc` 的树其实完好 ⇒ 按**源码存在性**判（38 棵 worktree 全量实测：**0 棵功能缺失**、3 棵完全未补，后者在全量里是**响的收集错**、不是静默）；② **worktree 路径过深会按"长度"打红**——`tests/test_tainted_mask/…::test_add_taint_records_stack` 断言 `用例名 in record.first_stack`，而 `first_stack` 是**被按长度截断**的（`.venv\Lib\site-packages\pluggy\_callers…` + 长树名把用例名挤出预算）⇒ 与"路径含非法字符"无关，**是截断**；诊断同类红先看那个串**是否被截断**。
    ⚠️ **拷贝的快照会旧（2026-10-17 实测 · 本族第三次命中）**：三类资源里那两个 **plugin gitlink 的内容会随"插件仓前进"而变旧** —— 建树时 `robocopy` 拷的是**那一刻的快照**，之后插件仓的新提交**不会**自动进来。实测（`version-floor-soften` 树，`robocopy` 自**主仓快照**）：`test_legacy_compat_visibility_e2e` 两条报 `AttributeError: module 'maibot_team_v1_compat.compat_bridge' has no attribute 'build_runner_env'`（该函数是**在插件仓里**新加的）、`test_manifest_v3_support[maibot-team.napcat-adapter]` 报缺 `_manifest.json`（快照早于那次改名）⇒ **三条都不是代码问题，是快照旧**。⇒ **规则**：**建树后、以及插件仓有新提交后，重新 materialize 这两个 gitlink**（`robocopy /E` 重拷即可；**别用 `xcopy`**，见上）；否则**测的是旧插件**。⭐ **这类红的特征 = 报错指向"插件文件/插件属性名"，而你的改动根本没碰插件** —— 见到就往这里查。⚠️ 与 `#37` 的"未 materialize ⇒ `git -C` 落回父仓"是**同一族的两件事**：那条讲"看错对象"，这条讲"看的是旧快照"。
    ⚠️ **补 `.shared` 时排除 `.git`**（`robocopy /E` 会连隐藏文件一起拷 ⇒ 做出一个**对主仓隐身**的 fork：在副本里 commit 落不到真身）；**要提交产出就直接去主仓 `.shared` 写**，树里的 `.shared` 只作**读**用（2026-10-17 实测：空壳 `.shared` 会让 `git -C` **落回树根** ⇒ 那两条 status/diff **答的是整棵树**，而 diff 对 `.shared` 路径看起来像"没人改" ⇒ **能产出可信的假证据**）。
35. **`mingtang` 里跑 `npm run build` 就是**一次即时上线**——前端与后端会当场版本错配（挂载解决文件，不解决进程）**（2026-10-16 配置体系轮实测）：`docker-compose.yml:64` 把**宿主机 `./mingtang/dist` 只读挂进容器**（注释原文："宿主机 npm run build 后即时生效"），前端静态资源**没有镜像内副本**（Dockerfile 内零 `mingtang` 字样）。⇒ **构建即部署**：一 build，运行中的服务立刻开始服务新前端；**而后端进程仍是启动时载入的那份代码**（改 `src/**` 不重启**不生效**）。
    **本轮真实风险**：主干前端已改调 `/config/get` + `/config/mutate`，而活服务进程（02:02 启动）**没有这两个路由**（`/openapi.json` 406 条路径实测无、只读探测返回 405 相合）⇒ **重启容器之前，任何一次 `npm run build` 都会把「模型配置页」打断**。
    规则：① **验证前端别在主 checkout 里 build**——在 **worktree** 里 build（各树有各自的 `dist`，不挂进容器）；② 确需在主 checkout build 时，**先确认容器后端已含前端要用的路由**（`docker exec maim-bot-core sh -c "curl -s localhost:<port>/openapi.json | grep -c config/mutate"`）；③ **前端改动与后端路由上线必须同批**：**后端先重启、前端后 build**；④ 排查"页面 404/405 但源码明明有那个端点"时，先问**"跑的是哪份代码"**——**挂载只解决文件，不解决进程**。
36. **`ruff check <显式文件>` 的判据必须绑定文件集——`ruff check x.json` 会把它按 Python 解析 ⇒ 全是假阳性**（2026-10-17 消息接缝轮 · P2① 段一验收）— 把生成物 `src/common/utils/session_id_vectors.json` 显式传给 ruff ⇒ **89 条假阳性**（88 条 `F821 undefined name: null` + 1 条 `B018 useless expression`）——**ruff 对显式传入的文件按 Python 解析，不看扩展名**。当时验收清单写的是"ruff 无新增"，而**这条命令本身不成立**（**是我们的检查清单错了，不是 ruff 的错**）。
    规则：① 验收口径里的"ruff 干净"**必须写明文件集**（`ruff check <列出的 .py>`），不许写成泛指的"ruff 干净"——否则换个文件集就不成立；② **别把生成物/数据文件喂给 linter**（`.json`/`.csv`/`.txt` 不在判据面内）；③ 命中数**离谱地大**时，先怀疑"**喂错了文件集**"，再怀疑代码（与 §七"**过滤器命中数太少要当症状查**"是同一条纪律的两端）；④ 本条属"**用法坑**"⇒ 记 `docs/pitfalls.md`，不进 `TOOL_ISSUES.md`（后者记工具缺陷，且由 WB 统一提交）。
37. **`git -C <未初始化的 submodule 目录>` 静默落回父仓 ⇒ 给的是"好看的假绿"**（2026-10-17 消息接缝轮 · P2① 段三）— worktree 里的 `plugins/maibot-team.napcat-adapter` 是 **gitlink（mode 160000）且该树里 submodule 未初始化（无 `.git`）**。往里写了两个新文件后：
    ```powershell
    git -C <wt>\plugins\maibot-team.napcat-adapter rev-parse --show-toplevel   # → 父仓路径（!.agents\worktrees\sessionid-vectors）
    git -C <wt>\plugins\maibot-team.napcat-adapter status --porcelain          # → 只有父仓的两行 M；那两个新文件一行都没有
    git -C <真插件仓> status --porcelain                                        # → 空
    ```
    **一句话**：它**静默落回父仓** ⇒ `status --porcelain` **看起来像"那仓干净"，其实根本没在看那仓**；⚠️ **更坏的是它会返回父仓的其它改动**——所以"**有输出也不等于在看目标仓**"。
    规则：① 判"某个子仓/子目录的状态"**先 `rev-parse --show-toplevel` 确认它在看谁**（这一步直接暴露）；② 对比两个仓的状态时**两边都要显式给路径**并**各自核 toplevel**；③ **未初始化 gitlink 目录里写东西 = 写进一个对宿主 git 隐身的副本**（`git status` 看不见 ⇒ **别拿它当"已落地"的证据**）；④ 与"扫描面取空的门禁"同族，**但多一层迷惑性：它给的是一个好看的假绿，而不是一个响的错**（凡"检查器返回干净"当真时，先问它**看的是谁**）。
     ⚠️ **同类实例（2026-10-17 实测，规则可推广）**：worktree 里的 gitlink/submodule **未 materialize** ⇒ ① `git -C` **落回父仓** ② **路径存在但里面是空壳**（`.shared` 那例：index gitlink `160000 c49987282`、根无 `.gitmodules` ⇒ 目录空、`git -C .shared …` 报 `fatal: no submodule mapping found`）③ **是旧代**（worktree 的 `pitfalls.md` 49 行、末条目 `#32`；主仓 `#38`）⇒ **"能 cd 进去" ≠ "文件在那" ≠ "是同一代"**。
     ⇒ **动子仓/子模块文件前先三件**：`git rev-parse --show-toplevel` 确认**在看谁** · **核对条目编号/字节数** · **确认已 materialize**。（三个实例即上列 ①②③，已在本条目内联给出）。
38. **CRLF/物化状态让"同一内容不同结论"——`git status` 干净 ≠ 被检物没被动过；靠改被检物过关就是假绿**（2026-10-17 消息接缝轮 · P2① 主仓 CRLF 缺陷）— 生成物 `src/common/utils/session_id_vectors.json` 是**生成物**（LF 规范形 `14214` 字节），而主仓工作区那份被**检出成 CRLF**（`CR=387 / LF=387 / size=14601`，差 **387 = 每行一个 CR**）。生成器 `--check` 拿**工作区字节**与**现算的 LF 字节**逐字节比 ⇒ 主仓 `test_table_is_not_stale` **FAILED**、`--check` exit 1，且诊断句**自相矛盾**：**"行数不同：表 387 行 / 生成 387 行"**（它本有"打印首个差异行"的能力，此处没用上）。**同一份内容，换个检出环境就不同结论**（Linux CI / LF 工作区绿，本机 CRLF 红）。
    **⚠️ 陷阱（本条最通用的一条）**：**"修法若靠改动被检物来过关，就是假绿。"** —— 验收**必须**是「**现有那份 CRLF 工作区文件**变绿」，**不是**「把文件重写成 LF 之后变绿」。若为了让测试过而顺手把生成物重新生成/改写一遍（LF），测试当然绿，但**它证明的是"我换了一份文件"，不是"判据对物化状态免疫"**。
    **⚠️ 另一层（同轮实测）**：`git status --short` / `git diff` **答不了"物化状态有没有变"**——路径属性 `text=auto / eol=lf` 会做 clean 过滤 ⇒ **387 个 CR 被系统性忽略**（原始哈希 `71bbd0f3…` ≠ blob `f1ffa808…`，但**去掉 CR 后逐字节 0 处不同**）。⇒ 判"被检物动没动过"**必须**用 **mtime + CR/LF 计数 + `git hash-object --no-filters`**。
    规则：① **判据与"被检物的物化状态"耦合时，先让判据归一化，别让被检物就范**（只归一**行尾**——大小写/空白/编码一律不动，否则"内容真被改"也会被放过）：行尾归一化后比对；② **诊断要打首个差异位置**（行号 + 两侧原文），**不许**打印"行数不同：N 行 / N 行"这种自相矛盾的措辞；③ **`.gitattributes` 的 `eol` 例外要写明理由**——它**不会**把**已物化**的工作区字节变回去（`eol` 只在下次检出 / `git add --renormalize` 时生效），**别让它冒充"这次变绿的原因"**；④ **验收前置要核"被检物当前物化状态"**（`CR/LF/size` + mtime），并在回报里**如实标**"它动过/没动过被检物"。
    **✅ 修法落地（2026-10-17 当日，主仓实测）**：① `check_table` 比对前 `\r\n`/孤立 `\r` → `\n`（**只碰行尾**）；② `.gitattributes` 给该生成物加 `src/common/utils/session_id_vectors.json text eol=lf`（**行内写明为何这与"不强制工作区"的既有约定相反**）；③ 诊断改为**首个差异行（行号 + 两侧原文）**，归一行数相同而逐行全等时退回**首个差异字符（行号 + 列号）**。**两侧各两条用例钉住**：CRLF 整份存盘 ⇒ **仍绿**；内容真改一行（行尾保持 LF）⇒ **仍红**。**验收 = 那份 CRLF 工作区文件本身**（`CR=387 / size=14601` 未动、未重新生成）由 FAILED → passed —— 正好把本条开头的"假绿"警告变成可执行判据。


   ⚠️ **引用同理**：跨文档/跨条目的引用**必须核落点存在**（"我引的那段话到底在不在那里"）——**引用也是一种『看着在』**。（实例：`#37` 的一句曾指向 `msg_seam_p2_sessionid_1017.md` §八，而 §八 对 `materialize`/`c49987282` 是 **0 命中** ⇒ 引用错，已改为内联给出。）
    ⚠️ **同族补丁（2026-10-17 红证实测，`march-7th`）**：`rev-parse --show-toplevel` 必须**精确等于**「提交发生地那个仓」的绝对路径 —— **"以 `/.shared` 结尾"会被骗过**：带副本 `.git` 的树里 toplevel = `…/worktrees/<树>/.shared`（**形似而错**）、`status` 返**空**（假净，真身是 ` M`）、哈希给**旧版**（`3D9A0DB8…` vs 真身 `A9EB8776…`）；空壳树里 toplevel **落回树根**、对 `.shared/<path>` 的 `status/diff` **一律空**。⇒ 三条判据：① **精确**比对 toplevel（别只判结尾）② 与主仓**交叉校验** `status`/哈希 ③ 不一致即**证据作废**（38 棵 worktree 实测：空壳 35 · 有内容无 `.git` 2 · 带副本 `.git` 1 ⇒ **37/38 会答错对象**）。
39. **共享中文 `.md` 被"文本模式读-写"改坏：破坏后仍是合法 UTF-8（只在子串层面非法）⇒ 解码检查发现不了**（2026-10-17 消息接缝轮 · 实测事故）
    - **现场**：`.shared/research/2026-10/msg_seam_p2_sessionid_1017.md` 被**第二个写者**改坏：**恰好 2 处 / 共 6 字节**（其余 38029 字节无损）——① 标题 `收真源：§五` 的 `源：` → `\n\n\`（**首行被截断**）② `## 一、…` 标题被拆成 3 行（`##` + 空行 + ` 一、…`）。
    - ⚠️ **最关键的一条**：**破坏后全文仍是合法 UTF-8**（第一处**只在子串层面**非法）⇒ **"能不能解码"这类检查恒为真、等于没有检查**；**必须查结构**（首个 `## ` 标题是否还在 / 有没有孤立 `##` / 章节数 / 与 HEAD 版交叉核对非空行）。
    - **成因假说**：**把 UTF-8 当单字节/单字符处理后再写回** ⇒ 恰好解释"6 字节、两处标题被切/被拆、其余无损"；典型来源是 **PowerShell 默认编码** 或 **`Get-Content | Set-Content`**。
    - **规则**：① **共享/中文 `.md` 一律字节级 I/O**（`[IO.File]::ReadAllBytes/WriteAllBytes`、python bytes），**禁 `Get-Content|Set-Content`**；② **写前重读 gate**（读到的内容与采样一致才落）；③ **改动前后各记哈希**（有并发写者时**行号会漂移** ⇒ 判据用**内容级**：非空行序列 + 章节标题门，**别只认行号**）；④ **同一活件尽量单写者**（少一个写者是最便宜的加固）。

   ⚠️ **同族最后一形态（最隐蔽）：相对路径的写 ⇒ 落到"进程 CWD"，而 CWD 是隐式参数**——实测（2026-10-17）：用**相对路径**调 .NET API，结果在**另一棵 worktree** 里误建了一个 **0 字节未跟踪文件**（已删；该树 `git status` 回空；**主仓目标文件 mtime/sha 全程未变**）。
   - **同族形态（共同根因：有些输入是隐式的 ⇒ "你写的对象" ≠ "你以为的对象"）**：① 未 materialize 的 submodule 上 `git -C` ⇒ **落回父仓**（好看的假绿）② 空壳 `.shared` ⇒ **落回树根** ③ 带副本 `.git` 的 `.shared` ⇒ **`toplevel` 看着对、内容却是旧代** ④ **相对路径的写** ⇒ **落到进程 CWD**。
   - **规则**：**任何写操作必须用绝对路径**（`[IO.File]::WriteAllText` 之类一律给全路径；脚本里**先 `Resolve-Path` 再写**）；**写完核对目标树的 `git status`**（防"落在别处"）。
   - ⭐ **负证据 vs 正证据**：**时间戳能证"我不在场"，不能证"你在场"** —— **正归因需要 owner / 锁 / per-writer 哈希，而负证据只需一个时间点**。（实测：`msg_seam` 的 `mtime 03:51:36` **早于**某支 `03:52:52` 起的所有写入 ⇒ 足以证"它没碰"；但要证"是谁碰的"⇒ **不可能**，因为无 owner/锁/per-writer 哈希。）
40. **测试里"真开真关网络资源"会把崩点放到**别的用例**上——Windows + `grpc.aio` 实测**（2026-10-17 插件运行时轮）— 现场：真建 `grpc.aio.server()` 再让绑定失败（原用例 `tests/plugin_runtime_v2/host/test_endpoint_is_running.py` 的 `test_false_and_released_when_bind_fails` 最初就长这样，端口 `0.0.0.0:8001`）⇒ **pytest per-test event loop 下后续用例吃 Windows access violation**（只选该用例 2/2）。现有规避 = 该用例改用 **mock 的 grpc server**；`HostEndpoint._discard_unstarted_server()` 只是**加固**、不是已证修法。
    - **机制（本轮定位，可复现的那一半）**：半建/悬挂的 `grpc.aio.Server` 活过创建它的 event loop 之后才被回收 ⇒ CPython 打 `Exception ignored while calling deallocator <function Server.__del__ ...>`：
      ```text
      File ".../grpc/aio/_server.py", line 219, in __del__
      File "src/python/grpcio/grpc/_cython/_cygrpc/aio/common.pyx.pxi", line 121, in schedule_coro_threadsafe
      File ".../asyncio/base_events.py", line 550, in _check_closed
      RuntimeError: Event loop is closed
      <sys>:0: RuntimeWarning: coroutine 'AioServer.shutdown' was never awaited
      ```
      ⇒ **`__del__` 里排不进协程 = 这对象的收尾就没人做了**（`shutdown` 从未 await）；它身上挂着 C-core 的真资源 ⇒ 收尾交给**另一个线程**（C-core 或解释器退出）时，Windows 上就可能变成 access violation —— 而**崩点在后续用例或解释器退出**，出错现场没有任何本用例的痕迹。
    - **实测边界（别把话说满）**：本机 2026-10-17 用裸 `grpc.aio.server()` 复现：① 绑定失败 + 悬挂（跨 loop）⇒ 4 用例全过；② 真 start + 不 stop ⇒ 4 用例全过、只在退出时打上面那段 `Server.__del__`；③ 40 轮混合压力 ⇒ 全过。**稳定复现的硬崩在本轮未取得** ⇒ 记的是"**机制 + 观测到的 deallocator 告警**"，不是"**每次必崩**"。⚠️ 另有一条**独立**的环境现象（同轮实测）：真 `HostEndpoint.start()` 用例在本机探针里**挂起 >45s**，卡在 `asyncio.run` 起新 loop 的 `socketpair/self-pipe`（`asyncio/windows_events.py` → `proactor_events._make_self_pipe` → `socket.py`），与 grpc 无关——**别把它当本条的复现**。
    - **规则**：① 测试**别真开真关网络资源**——用 mock/假 server，或把真实 server 放在**用例外**的 loop / fixture 里并保证成对清理；② **失败路径也必须停**（绑定失败 ≠ 不用收尾）——例外是**绑定都没成功时**：`grpc.aio.server()` 的构造函数**不建 native 对象**，`add_insecure_port` 抛（端口被占）时 server 也还不是"真 server"（实测 `HostEndpoint.start()` 此时 `Server.__del__` **不会**触发）；③ 别指望 `__del__` 收尾（它只能"尽力"，失败就是上面那条 ignored-exception）——**收尾必须是显式 await**；④ **别把"加固"说成"修好"**：`_discard_unstarted_server` 的定位保持"加固"，判据门说清是"哪一条不再崩"；⑤ 顺手一条**生产代码**发现（同轮实读）：`src/plugin_runtime_v2/host/endpoint.py:93-101` 的 `try` **只包住 `add_insecure_port` 之后的调用**，而 `add_insecure_port` 自己是抛点 ⇒ 端口被占时**根本不会走 `_discard_unstarted_server()`**，半建 server 就留在 `self._server` 上；按本条①③，这个端点若被长期持有并在解释器退出时才回收，收尾就归 `__del__` 管 —— **"加固"与"真收尾"之间还差这一行**。
43. **"扫空"会被误读成"不存在"——`rg` 默认看不见 gitignore 路径，而 `.agents/worktrees/.gitignore` 的内容就是 `*`**（2026-10-17 插件运行时轮 · compat-e2e；⚠️ **取证工具自身的盲区**）— 拿 `rg` 从 `.agents/worktrees` 往下扫一个符号 ⇒ "无命中"（退出码 1）⇒ 据此下了"全盘不存在"的结论；而那个符号其实就在其中一棵树的工作区里（另一条腿 `git log --all -S` 也空，因为它是**未提交**的）。两条腿看着互相印证，其实**同一类不可见**。
    - **机制（实测复现）**：`git check-ignore -v .agents/worktrees/<树>/src/.../plugin_loader.py` ⇒ 命中的是 **`.agents/worktrees/.gitignore:1:*`** ⇒ **每棵 worktree 的工作区都在 gitignore 里**；而 `rg` 默认尊重 `.gitignore` ⇒ **它根本不走进被忽略的路径**。同一条命令加 `--no-ignore` ⇒ **立刻 2 命中**。
    - **规则**：① **别从被忽略的根往下遍历**（必空）；**要对某棵树取证就把路径指到那棵树内部**（`rg <显式路径>` 会扫，不必加开关）；真要跨树全扫用 **`rg --no-ignore`**，并在结论里**写明用了它**；② **"没命中/扫空"本身不是证据** —— 除非同时说清**扫了哪些范围、含不含忽略项**（与 §七"全仓扫描要写口径"同源，但这次咬的是**取证工具自己**）；③ `git grep` / `git log -S` 只看**已提交**内容 ⇒ 对**未提交的工作区**天然无效 —— 它与 gitignore 盲区是**两个独立的失效面**，一次取证里**都要交代**；④ 判"某物不存在"前先问：**这个扫描器有没有它自己看不见的地方**。
    - **归属**：与"假绿（抽取器太窄 ⇒ 抽到 0 条照样绿）/ 假红（闸门与判据错配）/ 三义合一（恒空 stub、真没插件、插件全挂压成同一句）"同族，**第四格 = 扫描器自己看不见** ⇒ 共同根因：**检查无法分辨它必须分辨的状态**。


44. **批量改 CRLF 文件后必须复核 CR 计数：`edit` 工具会往 CRLF 文件里插 LF ⇒ 混合行尾**（2026-10-17）
   - 现场：11 个 `.py` 批量改动后，**一度 4 个文件出现混合行尾**（CRLF 文件里被插进 bare LF）；已全部归一（`CRLF bare-LF=0`）。
   - 规则：① 改 **`.py`（仓库约定 CRLF）** 之后，**逐文件复核 CR/LF 计数**（不要只看“能不能跑”）；② 与 `#39`（字节级 I/O）是近邻：**行尾与物化状态也是“看不见的输入”**；③ 判断“文件被谁改过”**不能只看 `git status`**（该族见 `#37`/`#38`）。
45. **`.pyc` 缓存：改脚本后同进程再 import 会读到旧逻辑 ⇒ 复核行为必先清缓存**（2026-10-17）
   - 现场：改 `scripts/n1_wiring_checker.py` 后**同进程**再 `import`，读到 `__pycache__` 里的**旧逻辑**，一度误判“`is_root` 不生效”。
   - 规则：**复核脚本行为前先删对应 `__pycache__`（如 `scripts/__pycache__/n1_wiring_checker*`）或用新解释器**；“我改了但它没变”这类现象**先怀疑缓存**，别先怀疑自己的改法。
46. **可被人依赖的补丁/交接必须落成文件 —— 且落成文件之后还要"对着实物核标识符"**（2026-10-17）
   - **证据 A（成因）**：那份"可照抄的补丁"**只活在回执与转述里** —— 全仓 `rg --no-ignore` **找不到那处接线** ⇒ 接手的人只能**照转述实现**（**不是照抄**）。
   - **证据 B（连带的坑）**：那份规格里用了两个**在那个树里根本不存在的标识符**（`LegacyCompatUnavailableError` / `self._compat_hook_error`）⇒ 接手的人按"**不新增类型**"改成**复用 `ImportError` + 现有信号**。
   - **规矩**：① **可被人依赖的补丁/交接必须落成文件**（回执 / 口头 / 转述**不算**落地）；② ⭐ **落成文件之后，还要"对着实物核标识符"** —— 文件名 / 类型名 / 字段名**必须在目标树里真的存在**（**文件不足以自证**）；③ 与"**引用必须核落点存在**"同族（**引用也是一种"看着在"**）。

47. **判据自己成为故障源：假红 + 降级路径 ⇒ 闸不只要求"能红"，还要求"误红不产生生产后果"**（2026-10-17 实测）
   - **事实链**：解析阶段第五支（**依赖 ID 格式非法**）**只记 `skips`、不进 `candidates`** ⇒ **三栏（activated / skipped / rejected）都不收** ⇒ 新加的**值域覆盖断言**把**合法输入**报成"**值域缺口**"并 `raise ValueError` ⇒ ⚠️ **bootstrap 于是把整条依赖解析降级为字母序**。
   - **判词**：这是"**假红 + 降级路径**" —— **比假绿更危险**：假绿只是**看不见**，假红**会改变生产行为**。
   - **第 5 形态**（与 恒假闸 / 恒真闸 / 三义合一 / 值域缺口 并列）：
     **判据自己成为故障源** ⇒ 三条要求：**(a) 能红** **(b) 不误红** **(c) ⭐ 误红时不许有生产后果**（**若"判据红了 ⇒ 走降级路径" ⇒ 那它就从检查变成了故障源**）。
   - **实测证据**（真输出。同一输入：1 个合法插件目录 `plugindir`，只有 `manifest.dependencies = ["invalid id!"]` 打错；复现跑 HEAD `30dfef000` 版 `dependency_resolver.py`、修后跑工作区当前版；除把临时绝对路径写作 `<tmp>` 外逐字照录）：
     ```text
     复现（HEAD 30dfef000 版 resolver）:
     [1] parse_candidate_manifests -> candidates: [] | skips: {'org.a': "依赖 ID 格式非法: ['invalid id!']"} | rejects: {}
     [2] compute_activation_plan -> ValueError: 值域缺口：以下候选目录既不在波次/跳过清单、也不在拒绝清单里 ⇒ 它们会从状态面消失：['plugindir']（共 1 个）。解析器的每个产出都必须落进 activated / skipped / rejected 三栏之一。
     [3] ActivationCoordinator.plan_startup(plugins_root, -1)（bootstrap.py:120 的生产入口）-> 同一个 ValueError 逸出:
         File "<tmp>\_head_resolver.py", line 514, in compute_activation_plan
           raise ValueError(
         ValueError: 值域缺口：以下候选目录既不在波次/跳过清单、也不在拒绝清单里 ⇒ 它们会从状态面消失：['plugindir']（共 1 个）。解析器的每个产出都必须落进 activated / skipped / rejected 三栏之一。
     修后（工作区当前版 resolver）:
     [1] rejects[org.a] = RejectEntry | reason=依赖 ID 格式非法: ['invalid id!']（目录 <tmp>\plugindir） | dir_path.name=plugindir
     [2] compute_activation_plan -> OK（不再抛『值域缺口』）; plan.waves=[] plan.skipped={} plan.rejected={'org.a': ('RejectEntry', 'plugindir')}
     [3] plan_startup -> 返回 OK（未降级）: rejected={'org.a': 'plugindir'}; coordinator._rejected={'org.a': 'plugindir'}
     ```
   - **修法**：让"第五支"这类产出**也落进三栏之一**（新增栏或补进既有栏），**并把该情形固化成用例**（"合法输入不得被判为缺口"）。
