# 角色扮演写作与回复自查

> 活文档。定位：写角色、审回复时的判据手册。
> 两类来源分开标注：**[社区]** = 角色扮演社区的实践与盲评，**[研究]** = 可查的论文。
> 两者的可信度不同，别混着引用。

---

## 一、Tavern 是什么

不是某个软件的名字，是**一整条产品线的通称**——从 2022 年的 TavernAI 开始，
现在泛指"本地部署的 LLM 角色扮演前端"。

### 谱系

| 时间 | 项目 | 说明 |
|---|---|---|
| 2022 | **TavernAI**（原版，2022-12 前后） | MIT，JavaScript。接 KoboldAI / NovelAI / **Pygmalion** / ChatGPT。首次把「角色卡 + lorebook」这套模型定下来 |
| 2023-02 | **SillyTavern** | 从 **TavernAI 1.2.8** fork 出来，AGPL-3.0，300+ 贡献者，至今独立开发。社区中文名叫「傻酒馆」 |
| 2024+ | **TavernAI 2** | 完全重写，300 MB 便携版，卡自带 Prompt Manager，支持 prompt 缓存与并发生成 |
| 2023+ | **RisuAI** / Agnai / 各类移动端 | 同一套卡格式的其他前端 |

### 角色卡是什么

一张 **PNG 图片**，人物的定义藏在图片的文本块里——**分享图片就等于分享角色**。

- 旧格式：文本块叫 `chara`
- V3 格式：文本块叫 `ccv3`，或者用 `.charx`（一个 ZIP，`card.json` 在根，素材放 `assets/{type}/`）

**⇒ 这个设计的后果**：一张图可能带隐藏指令，V3 甚至允许嵌入**代码资产**。
导入别人做的卡，等于导入可执行内容。

### 三个规范版本

| 版本 | 时间 | 标记 | 加了什么 |
|---|---|---|---|
| **V1** | 2023-05 之前的事实标准 | 无 | 六个字符串字段：name / description / personality / scenario / first_mes / mes_example |
| **V2** | 2023-05 ~ 06 | `chara_card_v2` / `version 2.0` | 全部嵌进 `data`；加 creator_notes、system_prompt、post_history_instructions、alternate_greetings、内嵌世界书、tags、creator、version、extensions |
| **V3** | 2024-04 ~ 07 | `chara_card_v3` / `version 3.0` | nickname、多语种 creator_notes、source、assets、group_only_greetings、创建/修改日期；世界书条目加 `use_regex` 与 `@@` 装饰器 |

V2 的诞生是**多项目协商**的结果：Pygmalion booru 与 characterhub.org 提供卡库，
Agnai / SillyTavern / RisuAI 做前端，ZoltanAI 做 V1 编辑器。V3 由 kwaroran（RisuAI 作者）主导。

### 字段什么时候进入提示词

这张表比字段名本身重要——**它决定了什么该写、什么不该写**。

| 字段 | 起始 | 行为 |
|---|---|---|
| name / description / personality / scenario | V1 | **永久，每次请求都发** |
| first_mes | V1 | **只发一次**（开场） |
| mes_example | V1 | 只在上下文有余量时保留，可强制常驻 |
| system_prompt / post_history_instructions | V2 | 填了就替换全局设置，留空则用全局 |
| alternate_greetings | V2 | 备选开场，每次是一条额外的 swipe |
| character_book | V2 | 前端**必须**默认使用，条目可进提示词 |
| creator_notes | V2 | **禁止用于提示词** |
| tags / creator / character_version | V2 | 不用于提示词 |
| extensions | V2 | 默认 `{}`；编辑器**不得**破坏自己不认识的键 |

---

## 二、社区版图

| 类型 | 代表 | 说明 |
|---|---|---|
| 主前端 | **SillyTavern** | 事实标准，扩展最多（表情精灵、自动摘要、图像生成、TTS、STscript 宏语言） |
| 卡库 | **Chub**（原 CharacterHub） | 最大的第三方卡库 |
| 卡库 | **JanitorAI** | 以"和别人的角色聊天"为产品形态 |
| 卡库 | **Pygmalion booru** | V2 规范里点名的卡库之一 |
| 讨论 | Reddit / Discord | SillyTavern 的 Discord 与 r/SillyTavernAI |
| 中文 | 傻酒馆文档站（sillytavern.wiki）等 | 翻译与教程为主 |

**⇒ 判断社区的成熟度看一件事：有没有出现"卡作者"这个职业身份。**
Chub 上已经有稳定的作者、署名惯例、CC BY 之类的许可约定——**这说明它过了爱好阶段。**

---

## 三、相关研究

这个领域不是没有学术工作，但方向很集中：**都在测「人格能不能维持」。**

### 核心现象：persona drift（人格漂移）

**[研究] EACL 2026 · arXiv:2512.12775**
*Persistent Personas? Role-Playing, Instruction Following, and Safety in Extended Interactions*

用 100+ 轮对话做长上下文评测，七个性价比最高的开源/闭源模型全中：

- **回归均值**：对话越长，模型越会丢掉角色特征，退回通用 AI 腔（典型的"作为一个 AI 语言模型"）。
- **量化结果**：到末轮，特征性人格模式的 token 占比**下降 41% 以上**。
- **目标导向对话漂移更快**：让模型一边维持角色一边完成任务，任务压力会把角色拽走。
- **人格-任务权衡**：人格淡去之后，指令跟随反而变好——**说明"像角色"和"好用"是互相拉扯的。**
- **结论一句**：*simply increasing context windows is insufficient to maintain character*。
  作者建议的方向是**专门的检索机制，持续把人格"提醒"给模型**。

### 三种缓解手段的实测对比

**[研究] IJSREM 2026 · Character-Driven LLMs**

| 手段 | 人格一致性 | 抗角色崩塌 |
|---|---|---|
| 纯 prompt | 一般（常规对话满分） | **差（3.00）** |
| **RAG 检索增强** | **最好（4.43）** | **最好（4.75）** |
| LoRA 微调 | **差**——数据集与人格不匹配就过拟合 | 差 |

**⇒ 结论：有策划好的记忆/检索，比微调更实用。**

### 强化学习路线

**[研究] NeurIPS 2025 · Consistently Simulating Human Personas with Multi-turn RL**

定义了三个自动指标（prompt-to-line / line-to-line / Q&A 一致性），用它们当奖励信号做多轮 RL，
**不一致减少 55%+**。**⇒ 需要训练资源，不是应用层的解法。**

### 对本项目的含义

**这三条合起来指向一个判断：记忆系统不只是"记住事实"，它是「维持人格」的主要手段。**

EACL 那篇的结论几乎就是在描述扩散激活该做的事——**持续把人格与关系"提醒"给模型**。
所以记忆检索的质量直接决定角色能不能撑过一百轮，这不是附加功能。

---

## 四、回复自查：七病灶

**[社区] 来源：`foreverse-app/character-card-skills` 的 `docs/before-after.md`**

那张背景是这样的：一张卡在结构化评分里拿了 **91.2 分**，被真实读者一眼判成 AI 写的，
而且读者点名了具体句子。作者把手术过程记下来，提炼出七条。

**核心判断：规格完美本身就是机器指纹。**
人类写手平铺信息、偶尔才俏皮一次；**均匀的机灵 = AI**。

| # | 病灶 | 判据 | 修法 |
|---|---|---|---|
| 1 | **引语点题** | 把事实包装成俏皮引语"盖章"，让读者觉得"这设定有味道" | 改回平铺陈述。全篇只许留 1 处当梗位 |
| 2 | **对仗翻转** | "不带 X，全是 Y" / "嘴上 X，行为 Y" 这类模具 | 改成随口会说的话 |
| 3 | **生造概念词** | "胜利锚点""保护色"这类机制词跑到可见文案里 | 机制词只许活在 system prompt 与世界书；可见处用日常说法 |
| 4 | **金句癖 + 空镜** | 三连排比、"记分牌的灯还停在上周的成绩页"、一串欲言又止的省略号 | 全删；段落允许平收甚至烂尾 |
| 5 | **伪精确数字** | "10 秒 98 / 0.01 秒 / 第 9 天 / 距锦标赛 40 天"式数字轰炸 | 保留的数字要口语化（"跑进 10 秒 9 几""还剩一个多月"）。**"半 X"量词模具同属此病**（停顿了半秒 / 退后半步 / 快了半拍） |
| 6 | **说明书腔外漏** | 把给模型的行为规格写进读者可见的文案 | 那句话搬进 system prompt，可见处删掉 |
| 7 | **零闲笔** | 每个细节都是功能件（牛奶=锚点、钉鞋=信号器），信息压强均匀 | **不是删细节，是加白长的**——一句不服务任何设定的废话 |

### 引语点题的例子

```
Before：大二摔栏摔的，她说那是「学费」。
After ：大二跨栏的时候摔过一次，锁骨下面留了道浅疤。
```

差别不在文笔，在**动机**：Before 在提醒你"这里有深意"，After 只是陈述。

### 零闲笔的例子

```
After 新增：「还站着干嘛？体育馆八点锁门，要走顺便帮我把灯关了。」
```

这句不服务任何设定。**人类写手会留自嗨的废话；全篇至少一处。**

---

## 五、终检法

**[社区] 工具替代不了的一条。**

> 把 description 和开场白**读出声**。凡是读到某句心里冒出「这句真妙」，
> 十有八九要改平——**妙感密度就是 AI 浓度**。

**台词不受此限**：毒舌人设的台词就该扎人。这条只治**旁白和介绍文字**。

---

## 六、三条硬判断

**1. 规格完美本身就是机器指纹**

v1 的每一处都符合"好卡"规格——细节具体、句句有信息、结构完整。**问题恰恰出在这。**

**2. 评分器满意 ≠ 人味**

那次 91.2 分是怎么来的：检测器**只扫开场白和示例对话**，`description` 与作者的话
**完全脱检**。**⇒ 评估如果只测某一层，漏掉的那层恰恰是最假的。**

**3. 别拿 LLM 当人味评委**

他们做过双盲：多数 LLM 评委把该卡 v1（反 AI 味 0 分）判成"更像真人"，
把社区人类热门卡判成 AI —— **因为 LLM 把细节密度当成了人味。**

**⇒ 这条包括我自己**：我说"读起来挺自然"不作数。

---

## 七、来源

| 内容 | 来源 |
|---|---|
| 七病灶、终检法、三条硬判断 | `foreverse-app/character-card-skills`（CC BY 4.0）的 `docs/before-after.md`；原作仓库 42★，含 15 张原创卡与 `score_card.py` 评分器 |
| persona drift 实证 | arXiv:2512.12775，EACL 2026 |
| 三种手段对比 | IJSREM 2026，*Character-Driven LLMs* |
| RL 路线 | NeurIPS 2025，*Consistently Simulating Human Personas* |
| Tavern 谱系与卡规范 | SillyTavern 官方文档；Character Card V2/V3 规范仓库；aiciety.net 与 aicompanionguides.com 的格式综述 |
