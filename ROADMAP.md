# ROADMAP —— Hermes 有、本项目还没做的能力

诚实记录差距,方便后续补全或评估是否值得做。已实现的能力见 [HERMES_PARITY.md](HERMES_PARITY.md)。

## 🟡 想做、暂未做

### Honcho dialectic 辩证式用户建模
- **Hermes**:用辩证式(反复质疑 / 修正)方法建用户模型,质量高、抗噪声。
- **现状**:只做单次 LLM 摘要增量合并(`update-user-profile.py`)。新观察和旧画像冲突时,靠 prompt 里「除非新对话明确否定」一句话裁决,没有显式的「提出假设 → 找反例 → 修正」回路。
- **质量差距**:中。
- **怎么做**:加一轮「自我质疑」prompt,或引入轻量 Honcho 风格的 representation 更新。

### embedding 相似度去重 / 合并
- **Hermes**:技能 / 记忆按语义聚类,近似主题自动归并。
- **现状**:`extract-skill.py` 只在 **slug 完全相同**时合并。LLM 给同一工作流起了不同 slug → 产生重复技能。
- **怎么做**:对 SKILL.md 的 description 做 embedding,余弦相似度超阈值时触发合并候选。本地可用 sentence-transformers,避免额外 API。

### 跨平台上下文「主动注入」
- **现状**:`cross-platform-context.py` 默认按需调用。
- **怎么做**:配 Claude Code SessionStart hook,会话一开始自动把该用户其他平台的近期摘要注入上下文。代码已支持,只差 hook 配置 + identity 自动发现。

## 🔴 故意不做(范围外)

### 隔离子 agent 并行执行
- **Hermes**:`spawn_subagent("研究 X")` 起完全独立的后台 agent,主对话照常,结果归并。
- **为何不做**:Claude Code 内置 Task 工具能起子 agent,但跑在同一上下文;真正的 RPC 级隔离要改 IM 桥让一个会话 fork 多个 claude 子进程,工程量大、和「轻量事后加工」的定位冲突。

### Hibernate / 按需唤醒(降本)
- **Hermes**:接 Modal / Daytona,闲时休眠,有消息再起,7×24 成本接近 0。
- **为何不做**:个人 Linux 机上做不到真休眠 —— IM 桥的长轮询需要本地进程一直在跑接消息。这条**必须**配事件触发的 serverless 平台才有意义;要做就把 IM 桥 Docker 化部署到 Modal,不属于本仓库。

### 200+ 模型路由(OpenRouter)
- **Hermes**:`hermes model gpt-5` 一行切。
- **为何不做**:本项目的核心卖点就是**复用 Claude 订阅、不烧 API**;引多模型路由就回到按 token 计费,违背初衷。需要时可在 `call_claude()` 处自行替换 CLI。

### RL trajectory / Atropos 集成
- **Hermes**:Nous 本职,每次对话都能变成训练数据。
- **为何不做**:个人记忆助手用不上,且需要训练基建。归档的 markdown(`data/archive/`)已是现成的 trajectory 来源,真要做可从这里导出。

### 更多 IM 桥接(WhatsApp / Signal 等)
- 取决于你接的那个 agent / IM 桥支持哪些平台,不在本项目范围。本项目只消费它导出的 JSON。

## 欢迎 PR

最有价值的三个方向:**embedding 去重**、**Honcho 辩证建模**、**SessionStart 自动注入**。前两个能显著提升「越用越精」的质量,第三个能让跨平台连续性真正无感。
