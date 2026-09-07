# Codex Advisor Skill

`advisor` 是一个支持按需自动触发和显式调用的 Codex Skill。它让当前主代理在遇到高影响架构取舍、证据冲突，或经过聚焦排查仍无法定位的问题时，按需创建一个只读的 GPT-6 Astra 顾问进行独立复核。

主代理仍然负责沟通、实现、验证和交付。顾问被要求只读：不修改文件、不执行外部变更、不继续创建子代理。

需要说明的是，Codex 的 `spawn_agent` 没有沙箱或只读参数，子代理默认继承主代理的全部工具（含写入）并且默认能继续分派。因此上述只读边界由任务包中的指令约束实现，不是平台强制隔离。本 Skill 把这些约束放在任务包首段以提高遵守率，但使用者应知道它属于约定而非沙箱。

## 设计来源

本 Skill 的多智能体协调思路参考了 OpenAI Codex 团队成员 Eric Provencher（[@pvncher](https://x.com/pvncher)）发布的 [Practical multi-agent orchestration in Codex](https://x.com/pvncher/status/2080707291603407077)。原文介绍了让协调者保持面向用户、按任务难度匹配推理强度、使用聚焦的新上下文分派子代理、避免重复工作，以及限制叶子代理继续分派等实用机制。

`advisor` 在这些机制上做了有意收窄：它不是通用的多代理执行团队，而是让主代理仅在确有价值时调用一个 GPT-6 Astra 只读顾问，并始终由主代理负责采纳判断、实施修改和完成验证。

这是一个独立的社区 Skill，不代表 OpenAI 官方发布、认证或背书，也不是对原文示例的逐字复制。

## 适用条件

- 适合：重要架构取舍、复杂故障定位、证据相互矛盾、需要独立第二意见。
- 不适合：简单修改、已知操作、常规实现，以及主代理已经能够直接解决的问题。
- 该 Skill 不会自动更换当前主模型；复杂取舍、证据冲突或聚焦排查卡住时可按需触发，简单任务直接完成。

## 环境要求

- 支持本地 Skills 的 Codex 环境。
- 在 `~/.codex/config.toml` 中启用多代理：

  ```toml
  [features]
  multi_agent = true
  ```

  这会启用 `spawn_agent`、`wait_agent`、`close_agent` 等工具。
- 账号和当前运行环境的模型覆盖列表中包含 `gpt-6-astra`（侦察员用 `gpt-5.6-sol`）。该列表由运行环境提供，在部分环境下可能为空。
- 安装前自检：

  ```bash
  grep -A3 '^\[features\]' ~/.codex/config.toml
  python3 -c "import json;print([m['slug'] for m in json.load(open('$HOME/.codex/models_cache.json'))['models']])"
  ```

- 如果 Astra 或协作工具不可用，Skill 会说明具体限制，并由当前主代理继续完成仍可完成的工作，不会静默替换模型。

## 安装

### 方法一：让 Codex 安装（推荐）

在 Codex 桌面端输入 `/`，选择 `skill-installer`，然后发送：

```text
请安装这个 Skill：
https://github.com/yuanCodeLab/codex-advisor-skill/tree/main/advisor
```

也可以直接使用文本形式：

```text
$skill-installer 请安装这个 Skill：
https://github.com/yuanCodeLab/codex-advisor-skill/tree/main/advisor
```

安装完成后，从下一轮对话开始使用。

### 方法二：运行内置安装脚本

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --url "https://github.com/yuanCodeLab/codex-advisor-skill/tree/main/advisor"
```

默认安装位置为：

```text
${CODEX_HOME:-~/.codex}/skills/advisor
```

安装器不会覆盖已经存在的 `advisor` 目录。更新前请先备份或移走旧目录，再重新安装。

### 方法三：手动安装

下载本仓库后，把完整的 `advisor` 目录复制到：

```text
~/.codex/skills/advisor
```

请保留以下目录结构：

```text
advisor/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── README.md
├── references/
│   ├── metrics.md
│   └── comparison.md
└── scripts/
    ├── log_event.py
    └── collect_usage.py
```

## 版本

本 Skill 通过 Git tag / GitHub Release 标记版本。Codex 的 frontmatter 校验器只接受 `name`、`description`、`license`、`allowed-tools`、`metadata`，因此 SKILL.md 中不写 `version` 字段。更新前请查看仓库 Releases 页确认变更。

## 使用

该 Skill 支持按需自动触发，无需每次手动选择；自动触发不代表一定创建顾问。也支持显式选择。Codex 桌面端推荐输入 `/` 打开菜单，选择 `advisor`，然后填写任务；也可以直接在消息中输入 `$advisor`。两种方式都会显式调用同一个 Skill。

### Codex 桌面端

1. 在输入框中输入 `/`。
2. 从菜单中选择 `advisor`。
3. 在插入的 Skill 后面填写任务并发送。

### 一般调用

```text
$advisor 帮我分析这个技术方案，必要时请 Astra 做一次只读复核。
```

### 架构取舍

```text
$advisor 我正在比较方案 A 和方案 B。
目标是：……
验收条件是：……
约束是：……
相关文件是：……
请在确有价值时调用 Astra 顾问，只读分析，不修改文件。
```

### 疑难排查

```text
$advisor 这个问题经过以下排查仍未定位：
1. 已检查……
2. 已尝试……
3. 当前证据……

请判断是否需要 Astra 顾问，并给出关键风险和最小必要验证建议。
```

## 运行方式

1. 主代理先判断问题是否真的需要独立顾问。
2. 如果问题属于常规任务，主代理直接完成，不创建顾问。
3. 如果独立复核有明确价值，主代理用 `spawn_agent` 创建一个 `gpt-6-astra` 顾问（`fork_turns="none"`，任务包首段写明只读约束）。
4. 顾问运行期间主代理推进不依赖其结论的工作，只在结论成为关键路径阻塞项时 `wait_agent`。
5. 拿到结论后立即 `close_agent` 释放并发额度——已完成的代理在关闭前仍占用槽位。
6. 主代理审查顾问建议，只采纳有证据支持的内容，并完成必要验证。
7. 交付时说明实际调用了什么模型、顾问解决了什么、采纳了什么以及验证结果。

## 本地效果记录

显式调用执行实际任务，或自动进入顾问流程时，Skill 会把开始和结束事件追加到：

```text
${CODEX_HOME:-~/.codex}/advisor-metrics/events.jsonl
```

写入由 `advisor/scripts/log_event.py` 完成，它负责 UUID、UTC 时间戳、JSON 序列化、追加写入和写后校验；查看汇总用 `python3 scripts/log_event.py report`。用量与费用折算是另一套按需流程，见下节。

记录用于评估顾问是否被调用、任务验收结果和可获得的运行数据。它不会保存源码、完整提示词、完整对话、凭证或工具原始输出。没有实际用量证据时，不会虚构 token、费用或节省比例。

关闭与清理：设 `ADVISOR_METRICS=0` 即可完全关闭记录；日志无自动轮转，可随时删除 `events.jsonl` 或整个 `advisor-metrics/` 目录。在只读沙箱等无法写入的环境中，脚本会返回非零并说明原因，任务继续执行，最终如实报告未记录。

## 推理强度与按需统计

顾问默认使用 Medium，复杂逻辑使用 High，特别困难的问题可选 XHigh 或 Max；不逐档试跑。Ultra 不作为普通只读顾问的自动升档终点。高强度选择会说明理由。

普通任务仅记录基础指标和关联 ID。只有你要求汇总、查看用量或计算成本时才运行采集器。API 情景估算不是实际账单；父子代理计数互斥尚未验证时，不合计为任务总价。价格快照标注日期，统计金额时按规则核对。

## 可选单代理对照

日常只跑一次，不自动添加对照字段或重复执行。明确指定对照任务时，才记录编号、组别、起点和验收条件：

```text
这次是 advisor 对照任务，编号 import-01，模式 solo。
只由主代理完成，不调用子代理；记录基础指标和对照条件。
任务：……
起点与输入资料：……
验收条件：……
```

在相同起点的独立任务或工作副本中，使用相同需求和验收条件，将模式改为 `advisor`，按需使用顾问。第二组不要读取第一组的答案。两次运行会分别消耗用量，不会由 Skill 自动启动第二次。

完成后发送：

```text
比较编号 import-01 的 solo 与 advisor 运行效果。
```

只有请求比较时才分析。缺一组标记“缺少对照”；起点、输入或验收无法核实时仅并列展示。同一编号有多次运行时需指定配对的 run_id，不挑选最好成绩。完整用量无法归属时不计算节省比例。

更多说明见 [Skill 使用说明](advisor/README.md) 和 [对照规则](advisor/references/comparison.md)。此功能已完成静态格式与链接检查，尚未验证真实双跑效果。
