# 效果记录规则

## 保存与任务边界

- 本地保存到 `${CODEX_HOME:-~/.codex}/advisor-metrics/events.jsonl`，先展开实际路径。目录不存在时创建。用脚本的 JSON 序列化和追加模式写入 UTF-8，每个事件一行，不用 shell 插值拼接 JSON。不要覆盖既有记录，也不写入技能安装目录。
- 每次显式调用产生唯一 UUID `run_id`，开始时记录 `start` 事件；交付、阻塞或取消时用同一 ID 追加 `end` 事件。同一轮任务中的补充消息归属同一记录；已结束后的新工作生成新 ID。连续对话中仅讨论规则不算执行样本。
- 获取真实 UTC 时间，不猜时间；从开始记录到结束记录计算 `elapsed_seconds`，含工具与用户等待，不称为纯模型耗时。明确的用户等待可另记，但无法测量则为 null。
- 强制中断可能来不及写入结束事件。汇总时保留为未结束样本，不计作成功，也不补造结束时间。上下文压缩后只查当前 run_id 的必要记录，不扫描其他会话。
- 若写入失败或文件工具不可用，任务继续，最终说明未记录及原因，不能声称保存成功。写入后解析最后追加的事件确认 run_id、事件类型和格式。

## 事件字段

两个事件都包含：`schema_version: 1`、`run_id`、`event`、`timestamp_utc`、`skill: "advisor"`。

开始事件额外包含：

- `task_label`：简短、脱敏的任务类别，不保存完整需求、客户名称或业务数据。
- `main_model` 和 `main_effort`：仅记录当前环境可确认的值，否则 null。

结束事件额外包含：

- `status`：completed、blocked 或 cancelled；完成不等于用户确认满意。
- `elapsed_seconds`、`user_wait_seconds`：实测值或 null。
- `agents`：每个实际创建的子代理记录 role、model、effort、followup_count、contribution、adoption（yes/partial/no/unknown）。调用失败另记 `spawn_failures`，不能算成功创建。没有创建时 agents 为空数组。
- `acceptance`：passed、partial、failed、not_checked；`verification_summary` 写简短的实际检查结果，区分静态检查、运行测试和用户确认。
- `user_corrections`：本任务可见的用户纠错次数；新需求或偏好变化不算错误。`rework_cycles`：由于缺陷或验收失败而实际重做的轮次；首次实现和正常探索不算返工。无法判断填 null，不能把没观察到的数据写成零。
- `usage`：对象，包含 input_tokens、output_tokens、cached_input_tokens、cache_write_tokens、cost_amount、currency、source、scope。仅填工具或运行时直接返回且能归属本次任务的数据，缺失字段为 null；scope 取 whole_run、partial 或 unavailable。不得把部分子代理用量标为整个任务用量，也不得重复计数推理 token。
- `assessment`：可选的一句主代理判断，明确这是主观评价，不能虚构“避免了几次返工”或“节省百分比”。

不自动读取账户总额度；它可能混入其他任务。不搜索会话原始日志、凭证或其他项目来补齐用量。不保存源码、完整提示词、完整对话或工具原始输出。

## 报告与汇总

结束时用一句话说明已记录及关键缺失项，不重复展示整个 JSON。用户询问效果时读取该本地日志，按 run_id 配对，报告样本数、未结束数、实际验收结果、耗时及有完整数据的用量；分开报告未知项。

仅记录 advisor 任务不能证明比单代理更好或更省。比较需要用户提供或授权采集相同口径的基线任务，且难度与验收条件相近。不得根据主观贡献或部分 token 推导节省比例。
