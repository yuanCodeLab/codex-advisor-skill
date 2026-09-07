#!/usr/bin/env python3
"""advisor 效果记录器。

把 start / end 事件追加到 ${CODEX_HOME:-~/.codex}/advisor-metrics/events.jsonl。
由主代理在任务开始和结束时各调用一次，不需要额外子代理。

设计约束（对应 references/metrics.md）：
- 时间戳取真实 UTC，不由模型填写。
- run_id 为脚本生成的 UUID4。
- JSON 由 json.dumps 序列化，不做 shell 字符串拼接。
- 追加写入，写后回读最后一行校验。
- 写入失败时返回非零并在 stderr 说明原因，调用方据此如实报告"未记录"。
- 环境变量 ADVISOR_METRICS=0 可完全关闭记录（退出码 0，输出 disabled）。

用法：
  log_event.py start --task-label refactor [--main-model X] [--main-effort Y]
      -> stdout 输出 run_id

  log_event.py end --run-id <id> --status completed \
      [--acceptance passed] [--verification-summary "..."] \
      [--agents-file agents.json] [--usage-file usage.json] \
      [--user-corrections N] [--rework-cycles N] [--assessment "..."]

  log_event.py report [--limit N]
      -> 按 run_id 配对汇总本地日志

字段语义见 references/metrics.md。本脚本只负责写入与配对，不做效果推断。
"""

import argparse
import datetime
import json
import os
import pathlib
import sys
import uuid

SCHEMA_VERSION = 1
SKILL = "advisor"

STATUS_CHOICES = ("completed", "blocked", "cancelled")
ACCEPTANCE_CHOICES = ("passed", "partial", "failed", "not_checked")

USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "cost_amount",
    "currency",
    "source",
    "scope",
)


def metrics_enabled() -> bool:
    return os.environ.get("ADVISOR_METRICS", "1").strip().lower() not in (
        "0",
        "false",
        "off",
        "no",
    )


def events_path() -> pathlib.Path:
    codex_home = os.environ.get("CODEX_HOME")
    base = pathlib.Path(codex_home).expanduser() if codex_home else pathlib.Path.home() / ".codex"
    return base / "advisor-metrics" / "events.jsonl"


def now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def die(msg: str) -> "None":
    print(f"advisor-metrics: {msg}", file=sys.stderr)
    sys.exit(1)


def append_event(event: dict) -> pathlib.Path:
    """追加一个事件并回读校验。任何失败都抛异常给调用方处理。"""
    path = events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, sort_keys=True)
    if "\n" in line:
        raise ValueError("serialized event contains a newline")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())

    # 回读最后一行，确认 run_id、事件类型和格式都写对了。
    with open(path, "r", encoding="utf-8") as fh:
        last = None
        for last in fh:  # noqa: B007 - 只要最后一行
            pass
    if last is None:
        raise IOError("file is empty after append")
    parsed = json.loads(last)
    if parsed.get("run_id") != event["run_id"] or parsed.get("event") != event["event"]:
        raise IOError("last line does not match the event just written")
    return path


def load_json_file(path: str, what: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        die(f"failed to read {what} from {path}: {exc}")


def cmd_start(args) -> None:
    run_id = str(uuid.uuid4())
    event = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "event": "start",
        "timestamp_utc": now_utc(),
        "skill": SKILL,
        "task_label": args.task_label,
        "main_model": args.main_model,
        "main_effort": args.main_effort,
    }
    try:
        append_event(event)
    except Exception as exc:  # noqa: BLE001
        die(f"start not recorded: {exc}")
    print(run_id)


def cmd_end(args) -> None:
    agents = load_json_file(args.agents_file, "agents") if args.agents_file else []
    if not isinstance(agents, list):
        die("agents file must contain a JSON array")

    spawn_failures = (
        load_json_file(args.spawn_failures_file, "spawn_failures")
        if args.spawn_failures_file
        else []
    )

    usage = {k: None for k in USAGE_KEYS}
    if args.usage_file:
        supplied = load_json_file(args.usage_file, "usage")
        if not isinstance(supplied, dict):
            die("usage file must contain a JSON object")
        unknown = set(supplied) - set(USAGE_KEYS)
        if unknown:
            die(f"unknown usage keys: {', '.join(sorted(unknown))}")
        usage.update(supplied)
    if usage["scope"] is None:
        usage["scope"] = "unavailable"

    elapsed = None
    start_ts = find_start_timestamp(args.run_id)
    if start_ts is not None:
        try:
            end_dt = datetime.datetime.fromisoformat(now_utc())
            elapsed = int((end_dt - datetime.datetime.fromisoformat(start_ts)).total_seconds())
        except Exception:  # noqa: BLE001
            elapsed = None

    event = {
        "schema_version": SCHEMA_VERSION,
        "run_id": args.run_id,
        "event": "end",
        "timestamp_utc": now_utc(),
        "skill": SKILL,
        "status": args.status,
        "elapsed_seconds": elapsed,
        "user_wait_seconds": args.user_wait_seconds,
        "agents": agents,
        "spawn_failures": spawn_failures,
        "acceptance": args.acceptance,
        "verification_summary": args.verification_summary,
        "user_corrections": args.user_corrections,
        "rework_cycles": args.rework_cycles,
        "usage": usage,
        "assessment": args.assessment,
    }
    try:
        append_event(event)
    except Exception as exc:  # noqa: BLE001
        die(f"end not recorded: {exc}")
    print(json.dumps({"run_id": args.run_id, "elapsed_seconds": elapsed}, ensure_ascii=False))


def iter_events():
    path = events_path()
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def find_start_timestamp(run_id: str):
    """只查目标 run_id 的开始时间，不扫描其他会话的记录内容。"""
    for ev in iter_events():
        if ev.get("run_id") == run_id and ev.get("event") == "start":
            return ev.get("timestamp_utc")
    return None


def cmd_report(args) -> None:
    starts, ends = {}, {}
    for ev in iter_events():
        rid = ev.get("run_id")
        if not rid:
            continue
        (starts if ev.get("event") == "start" else ends)[rid] = ev

    order = list(starts)
    if args.limit:
        order = order[-args.limit :]

    unfinished = [r for r in order if r not in ends]
    finished = [r for r in order if r in ends]

    acceptance_counts, spawned_runs = {}, 0
    for rid in finished:
        acc = ends[rid].get("acceptance") or "not_checked"
        acceptance_counts[acc] = acceptance_counts.get(acc, 0) + 1
        if ends[rid].get("agents"):
            spawned_runs += 1

    usable_usage = [
        rid
        for rid in finished
        if (ends[rid].get("usage") or {}).get("scope") == "whole_run"
    ]

    print(
        json.dumps(
            {
                "events_file": str(events_path()),
                "samples": len(order),
                "finished": len(finished),
                "unfinished": len(unfinished),
                "runs_that_spawned_an_agent": spawned_runs,
                "acceptance": acceptance_counts,
                "runs_with_whole_run_usage": len(usable_usage),
                "note": "未结束样本不计作成功；无基线对照时不得据此推导节省比例。",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="advisor 效果记录器")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="记录任务开始，输出 run_id")
    p_start.add_argument("--task-label", required=True, help="简短脱敏的任务类别")
    p_start.add_argument("--main-model", default=None)
    p_start.add_argument("--main-effort", default=None)
    p_start.set_defaults(func=cmd_start)

    p_end = sub.add_parser("end", help="记录任务结束")
    p_end.add_argument("--run-id", required=True)
    p_end.add_argument("--status", required=True, choices=STATUS_CHOICES)
    p_end.add_argument("--acceptance", default="not_checked", choices=ACCEPTANCE_CHOICES)
    p_end.add_argument("--verification-summary", default=None)
    p_end.add_argument("--agents-file", default=None, help="JSON 数组文件")
    p_end.add_argument("--spawn-failures-file", default=None, help="JSON 数组文件")
    p_end.add_argument("--usage-file", default=None, help="JSON 对象文件")
    p_end.add_argument("--user-wait-seconds", type=int, default=None)
    p_end.add_argument("--user-corrections", type=int, default=None)
    p_end.add_argument("--rework-cycles", type=int, default=None)
    p_end.add_argument("--assessment", default=None)
    p_end.set_defaults(func=cmd_end)

    p_report = sub.add_parser("report", help="按 run_id 配对汇总本地日志")
    p_report.add_argument("--limit", type=int, default=None)
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()

    if not metrics_enabled():
        print("disabled (ADVISOR_METRICS=0)")
        return

    args.func(args)


if __name__ == "__main__":
    main()
