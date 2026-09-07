# 效果记录规则

## 保存与任务边界

- 写入统一用 `scripts/log_event.py`（`start` / `end` / `report`），它负责 UUID、真实 UTC 时间戳、JSON 序列化、追加写入和写后回读校验。不要手工拼接 JSON。
- 本地保存到 `${CODEX_HOME:-~/.codex}/advisor-metrics/events.jsonl`，脚本自动展开路径并创建目录，不覆盖既有记录，也不写入技能安装目录。
- 显式调用执行实际任务，或自动进入顾问流程时，产生唯一 UUID `run_id` 并记录 `start` 事件；交付、阻塞或取消时用同一 ID 追加 `end` 事件。同一任务内再次显式调用或自动触发不重复建记录；已结束后的新工作生成新 ID。仅考虑技能但未进入流程、技能解释、修改和汇总不算执行样本。
- 若任务进行中才自动触发，以进入顾问流程时为计时起点，不倒填之前的耗时。汇总需区分整项任务与顾问阶段计时，不能将两者直接比较为任务提速。
- 获取真实 UTC 时间，不猜时间；从开始记录到结束记录计算 `elapsed_seconds`，含工具与用户等待，不称为纯模型耗时。明确的用户等待可另记，但无法测量则为 null。
- 强制中断可能来不及写入结束事件。汇总时保留为未结束样本，不计作成功，也不补造结束时间。上下文压缩后只查当前 run_id 的必要记录，不扫描其他会话。
- 若写入失败或文件工具不可用，任务继续，最终说明未记录及原因，不能声称保存成功。脚本会返回非零并在 stderr 说明原因（例如只读沙箱下的 Permission denied），据此如实报告。
- 关闭与清理：`ADVISOR_METRICS=0` 完全关闭记录；日志无自动轮转，可随时删除 `events.jsonl` 或整个 `advisor-metrics/` 目录。

## 事件字段

两个事件都包含：`schema_version: 1`、`run_id`、`event`、`timestamp_utc`、`skill: "advisor"`。以下字段通过脚本参数传入：

```bash
RUN_ID=$(python3 scripts/log_event.py start --task-label <脱敏类别> \
  --invocation explicit|automatic --trigger-reason "<进入流程的原因>" \
  --timing-scope whole_task|advisor_phase \
  [--main-model X] [--main-effort Y] [--thread-id T] [--turn-id U] [--rollout-path P])

python3 scripts/log_event.py end --run-id "$RUN_ID" --status completed \
  --acceptance passed --verification-summary "<实际检查结果>" \
  [--agents-file agents.json] [--usage-file usage.json] \
  [--user-corrections N] [--rework-cycles N]
```

未确认的值一律省略（记为 null），不猜测。对照任务的 `--comparison-id` / `--mode` / `--comparison-conditions-file` 见 [对照规则](comparison.md)，两者必须同时给出。

开始事件额外包含：

- `task_label`：简短、脱敏的任务类别，不保存完整需求、客户名称或业务数据。
- `main_model` 和 `main_effort`：仅记录当前环境可确认的值，否则 null。
- `invocation`：explicit 或 automatic；`trigger_reason`：简短说明进入流程的原因；`timing_scope`：whole_task 或 advisor_phase，开始时已在执行任务则为 advisor_phase。旧记录缺失这些字段时按未知处理。

结束事件额外包含：

- `status`：completed、blocked 或 cancelled；完成不等于用户确认满意。
- `elapsed_seconds`、`user_wait_seconds`：实测值或 null。
- `agents`：每个实际创建的子代理记录 role、model、effort、followup_count、contribution、adoption（yes/partial/no/unknown）。调用失败另记 `spawn_failures`，不能算成功创建。没有创建时 agents 为空数组。
- `acceptance`：passed、partial、failed、not_checked；`verification_summary` 写简短的实际检查结果，区分静态检查、运行测试和用户确认。
- `user_corrections`：本任务可见的用户纠错次数；新需求或偏好变化不算错误。`rework_cycles`：由于缺陷或验收失败而实际重做的轮次；首次实现和正常探索不算返工。无法判断填 null，不能把没观察到的数据写成零。
- `usage`：对象，包含 input_tokens、output_tokens、cached_input_tokens、cache_write_input_tokens、cost_amount、currency、source、scope。仅填工具或运行时直接返回且能归属本次任务的数据，缺失字段为 null；scope 取 whole_run、partial 或 unavailable。不得把部分子代理用量标为整个任务用量，也不得重复计数推理 token。
- `assessment`：可选的一句主代理判断，明确这是主观评价，不能虚构“避免了几次返工”或“节省百分比”。

不自动读取账户总额度；它可能混入其他任务。允许仅为当前 advisor 任务读取明确关联的本地 rollout 元数据与 token_count 事件；不读取或输出正文，不扫描无关项目或凭证。不保存源码、完整提示词、完整对话或工具原始输出。

## 报告与汇总

结束时用一句话说明已记录及关键缺失项，不重复展示整个 JSON。用户询问效果时运行 `python3 scripts/log_event.py report`，它按 run_id 配对 start/end，分开报告样本数、未结束数、验收结果与快照数；`usage_snapshot` 等其他事件不参与配对，未结束样本不计作完成。耗时及用量按已有完整数据报告，未知项单列。

仅记录 advisor 任务不能证明比单代理更好或更省。比较需要用户提供或授权采集相同口径的基线任务，且难度与验收条件相近。不得根据主观贡献或部分 token 推导节省比例。


## 用量采集与官方价格折算

使用技能目录内 `scripts/collect_usage.py`。不修改旧事件，也不把估算写成 usage.cost_amount 实际费用。仅讨论技能或汇总记录时不要新增执行样本。

1. 开始时在 start 事件记录已确认的 thread_id、turn_id、rollout_path；未知则 null。每次子代理创建或复用记录其对应 thread_id 和 turn_id。必要时仅查看已知会话目录的 session_meta、turn_context 和 task_started 来解析 ID，不能用完整对话搜索补齐。不能只凭时间接近判定归属。
2. 在本地 advisor-metrics/manifests/<run_id>.json 保存清单，每个实际主代理或子代理轮次一个 segment，格式如下。只加入可确切归属该任务的轮次；复用顾问不可加入其此前任务的轮次。

```json
{"run_id":"任务 UUID","segments":[{"role":"main","rollout_path":"已核实的绝对日志路径","turn_id":"实际轮次 ID"}]}
```

3. 仅当用户明确要求汇总使用效果、查看用量或计算成本时，执行 `python3 <技能目录>/scripts/collect_usage.py <清单路径>`，读取返回 JSON。普通任务执行及交付时不运行采集器，不计算金额。采集器只读日志，不写事件文件。验证 run_id 后由主代理用 JSON 追加写入 events.jsonl，事件类型为 usage_snapshot。清单缺失或关联不明确时标记未知，不猜测。
4. 只有用户主动要求统计时，才对其指定范围的已有清单采集或更新快照；再次使用 advisor 不触发补采、汇总或金额计算。尚未结束的轮次标记 partial，在用户下次要求统计时再更新。只保留每个 run_id 最新快照用于汇总；不要把多个快照相加。不要创建后台监控或为了采集等待当前轮次自行结束。
5. 快照分别列出各轮次模型、输入、缓存读取、缓存写入、输出，以及官方 API Standard 短/长上下文两种情景金额。它们不是价格上下界或真实服务档位。推理输出已包含在 output_tokens，不再次相加；缺失缓存写入量不按零处理。
6. 价格快照核对日期为 2026-09-07，来源为 https://developers.openai.com/api/docs/pricing 。支持 Astra、Sol、Terra、Luna（已于该日期对照官方页核对）。`gpt-reserve` 与 `gpt-5.3-codex-spark` 官方定价页未列出，前者是隐藏模型、后者不支持 API，快照以 `pricing_status` 说明原因而非静默留空；其他未知模型同样只给状态、不给金额。用户要求金额统计时，若首次估算或价格日期过旧，再核对官方价格；未核对时明确沿用标注日期的快照，不称当前价格。价格变化保留旧快照记录，不重写历史估算。
7. 尚未验证父代理用量是否包含子代理，所以 whole_run_cost 保持 null，展示各轮次折算即可。只有独立证据确认计数互斥、轮次覆盖完整后才可扩展为任务总价，不由模型主观推断。工具费用、订阅实际扣费、税费均不包含。

遇到计数重置、缺少基线、未完成或无样本时脚本输出问题标记，并不给完整金额。汇总须披露这些缺失，不能以情景估算声称省钱比例。

## 执行频率

普通任务仅追加开始/结束事件和必要的任务、代理关联清单；用量与费用留空，禁止结束时自动读取 rollout、运行采集器、汇总或折算金额。只有用户主动发出统计请求时才执行这些步骤。不要创建定时统计。
