# 效果记录规则

写入机制（UUID、UTC 时间、JSON 序列化、追加、写后校验、失败退出码）由 `scripts/log_event.py` 保证，本文件只定义**任务边界**和**字段口径**——这两项脚本无法代劳，必须由主代理判断。

## 任务边界

- 每次显式调用产生一个 `run_id`（`start` 子命令输出），交付、阻塞或取消时用同一 ID 调 `end`。
- 同一轮任务中的补充消息归属同一记录；已结束后的新工作生成新 ID。
- 连续对话中仅讨论规则不算执行样本。
- 强制中断可能来不及写结束事件。汇总时保留为未结束样本，不计作成功，也不补造结束时间。
- 上下文压缩后只查当前 run_id 的必要记录，不扫描其他会话。

## 存储与隐私

- 路径 `${CODEX_HOME:-~/.codex}/advisor-metrics/events.jsonl`，脚本自动创建目录，不写入技能安装目录。
- 只读沙箱或禁止写工作区外目录的环境中可能无法写入。脚本会返回非零并说明原因，任务继续，最终如实说明未记录。
- 日志无自动轮转，可直接删除该文件或整个 `advisor-metrics/` 目录。`ADVISOR_METRICS=0` 可关闭记录。
- 不保存源码、完整提示词、完整对话、凭证或工具原始输出。不自动读取账户总额度，它可能混入其他任务。

## 字段口径

`start` 事件：

- `task_label`：简短、脱敏的任务类别，不写完整需求、客户名称或业务数据。
- `main_model` / `main_effort`：仅记录当前环境可确认的值，否则留空。

`end` 事件：

- `status`：completed / blocked / cancelled。**completed 不等于用户确认满意。**
- `elapsed_seconds`：脚本按两次记录的时间差计算，含工具与用户等待，**不是纯模型耗时**。`user_wait_seconds` 无法测量时留空。
- `agents`：每个实际创建的子代理记录 role、model、effort、followup_count、contribution、adoption（yes/partial/no/unknown）。调用失败走 `--spawn-failures-file`，不能算成功创建。没创建时为空数组。
- `acceptance`：passed / partial / failed / not_checked。`verification_summary` 写简短的实际检查结果，**区分静态检查、运行测试和用户确认**。
- `user_corrections`：本任务可见的用户纠错次数；**新需求或偏好变化不算错误**。
- `rework_cycles`：因缺陷或验收失败而实际重做的轮次；**首次实现和正常探索不算返工**。
- 以上两项无法判断时留空（null），**不能把没观察到的数据写成零**。
- `usage`：仅填工具或运行时直接返回且能归属本次任务的数据，缺失字段留空；`scope` 取 whole_run / partial / unavailable。不得把部分子代理用量标为整个任务用量，不得重复计数推理 token。
- `assessment`：可选的一句主观判断，不得虚构"避免了几次返工"或"节省百分比"。

## 报告与汇总

- 结束时用一句话说明已记录及关键缺失项，不重复展示整个 JSON。
- 用户询问效果时运行 `scripts/log_event.py report`，它按 run_id 配对并分开报告未结束数与未知项。
- **仅记录 advisor 任务不能证明比单代理更好或更省。** 比较需要用户提供或授权采集相同口径、难度与验收条件相近的基线任务。不得根据主观贡献或部分 token 推导节省比例。
