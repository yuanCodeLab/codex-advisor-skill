# Codex Advisor Skill

`advisor` 是一个需要显式调用的 Codex Skill。它让当前主代理在遇到高影响架构取舍、证据冲突，或经过聚焦排查仍无法定位的问题时，按需创建一个只读的 GPT-6 Astra 顾问进行独立复核。

主代理仍然负责沟通、实现、验证和交付；顾问只提供判断依据，不修改文件、不执行外部变更，也不继续创建子代理。

## 适用条件

- 适合：重要架构取舍、复杂故障定位、证据相互矛盾、需要独立第二意见。
- 不适合：简单修改、已知操作、常规实现，以及主代理已经能够直接解决的问题。
- 该 Skill 不会自动更换当前主模型，也不会因为普通请求自动触发。

## 环境要求

- 支持本地 Skills 的 Codex 环境。
- 具备 `spawn_agent` 等协作子代理能力。
- 账号和当前运行环境能够使用 `gpt-6-astra`。
- 如果 Astra 或协作工具不可用，Skill 会说明具体限制，并由当前主代理继续完成仍可完成的工作。

## 安装

### 方法一：让 Codex 安装（推荐）

在 Codex 中输入：

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
└── references/
    └── metrics.md
```

## 使用

该 Skill 禁止隐式触发。每次使用时都需要明确输入 `$advisor`。

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
3. 如果独立复核有明确价值，主代理创建一个 `gpt-6-astra` 只读顾问。
4. 主代理审查顾问建议，只采纳有证据支持的内容，并完成必要验证。
5. 交付时说明实际调用了什么模型、顾问解决了什么、采纳了什么以及验证结果。

## 本地效果记录

每次显式调用 `$advisor` 时，Skill 会把开始和结束事件追加到：

```text
${CODEX_HOME:-~/.codex}/advisor-metrics/events.jsonl
```

记录用于评估顾问是否被调用、任务验收结果和可获得的运行数据。它不会保存源码、完整提示词、完整对话、凭证或工具原始输出。没有实际用量证据时，不会虚构 token、费用或节省比例。

## 为什么必须显式调用

调用额外顾问可能增加耗时、模型用量和协作复杂度。显式的 `$advisor` 相当于用户主动打开“独立专家复核”开关，可以避免普通问题误触发 Astra，也让效果记录的任务边界更清晰。
