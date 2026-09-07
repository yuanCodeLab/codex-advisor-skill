#!/usr/bin/env python3
"""Read only explicitly selected rollout turns; emit API-equivalent estimates."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

PRICES = {
    'gpt-6-astra': ([10, 1, 12.5, 50], [20, 2, 25, 75]),
    'gpt-5.6-sol': ([4, .4, 5, 20], [8, .8, 10, 30]),
    'gpt-5.6-terra': ([2, .2, 2.5, 12], [4, .4, 5, 18]),
    'gpt-5.6-luna': ([.2, .02, .25, 1.2], [.4, .04, .5, 1.8]),
}
# 已知模型但官方定价页未列出，逐个记明原因，避免与"用量字段缺失"混为一谈后静默跳过。
UNPRICED = {
    'gpt-reserve': 'not_on_public_pricing_page',      # supported_in_api 但 visibility=hide
    'gpt-5.3-codex-spark': 'not_api_supported',       # supported_in_api=False，本就无 API 价格
}
KEYS = ['input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens']

def pricing_status(values, model):
    if model is None:
        return 'model_unknown'
    if model in UNPRICED:
        return UNPRICED[model]
    if model not in PRICES:
        return 'model_not_in_price_table'
    if any(values[k] is None for k in KEYS):
        return 'usage_incomplete'
    i, c, w, o = [values[k] for k in KEYS]
    if min(i, c, w, o) < 0 or c + w > i:
        return 'usage_inconsistent'
    return 'priced'

def estimate(values, model):
    if pricing_status(values, model) != 'priced':
        return None
    i, c, w, o = [values[k] for k in KEYS]
    parts = [i-c-w, c, w, o]
    return {name: round(sum(n*p for n, p in zip(parts, rates))/1e6, 8)
            for name, rates in zip(['standard_short_usd', 'standard_long_usd'], PRICES[model])}

def collect(segment):
    target = segment['turn_id']
    previous = None
    current = None
    model = None
    thread = parent = None
    started = completed = False
    values = dict.fromkeys(KEYS, 0)
    issues = []
    samples = 0
    for line in Path(segment['rollout_path']).expanduser().open(encoding='utf-8'):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            issues.append('malformed_or_incomplete_line')
            continue
        p = e.get('payload', {})
        if e.get('type') == 'session_meta':
            thread = p.get('id')
            parent = p.get('parent_thread_id')
        if e.get('type') == 'turn_context':
            current = p.get('turn_id', current)
            if current == target:
                next_model = p.get('model')
                if model and next_model != model:
                    issues.append('model_changed_within_turn')
                model = next_model
        if e.get('type') != 'event_msg':
            continue
        kind = p.get('type')
        if kind == 'task_started':
            current = p.get('turn_id')
            if current == target:
                started = True
        if kind == 'task_complete' and p.get('turn_id') == target:
            completed = True
        if kind != 'token_count' or not p.get('info'):
            continue
        total = p['info'].get('total_token_usage')
        last = p['info'].get('last_token_usage')
        if not total:
            continue
        if current == target:
            if completed:
                issues.append('usage_after_completion')
            if previous is None:
                delta = total if last == total else None
                if delta is None:
                    issues.append('unknown_initial_baseline')
            else:
                delta = {k: total[k]-previous[k] if k in total and k in previous else None
                         for k in KEYS}
            if delta is not None:
                if any(v is not None and v < 0 for v in delta.values()):
                    issues.append('counter_reset')
                else:
                    if any(delta.get(k, 0) for k in KEYS):
                        samples += 1
                    for k in KEYS:
                        v = delta.get(k)
                        values[k] = None if v is None or values[k] is None else values[k]+v
        previous = total
    if not started:
        issues.append('start_not_found')
    if not completed:
        issues.append('pending_completion')
    if not samples:
        issues.append('no_usage_samples')
    complete = not issues
    return {'thread_id': thread, 'parent_thread_id': parent, 'turn_id': target,
            'role': segment['role'], 'model': model, 'completed': completed,
            'scope': 'selected_turn' if complete else 'partial', 'usage': values,
            'issues': sorted(set(issues)),
            'pricing_status': pricing_status(values, model) if complete else 'segment_incomplete',
            'api_equivalent': estimate(values, model) if complete else None}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('manifest', help='JSON with run_id and explicit segments')
    args = ap.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    segments = manifest['segments']
    identities = [(str(Path(s['rollout_path']).expanduser().resolve()), s['turn_id']) for s in segments]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate rollout/turn segment')
    results = [collect(s) for s in segments]
    print(json.dumps({'schema_version': 1, 'event': 'usage_snapshot',
        'run_id': manifest['run_id'], 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'price_date': '2026-09-07', 'price_source': 'https://developers.openai.com/api/docs/pricing',
        'currency': 'USD', 'cost_kind': 'api_equivalent_estimate_not_bill',
        'pricing_basis': 'Standard short/long scenarios, not observed service tier; excludes tool fees',
        'segments': results, 'whole_run_cost': None,
        'aggregation_note': 'Do not sum parent and child until exclusive accounting is verified.'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
