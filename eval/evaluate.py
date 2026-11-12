"""Run a model (base, or base + LoRA adapter) through the agent loop on the test tasks.

Each task runs in a fresh copy of its test world on the MockBackend, with greedy decoding.
Writes results/<name>.json (per-task details + aggregate metrics) and results/<name>.md.

  python eval/evaluate.py --name baseline
  python eval/evaluate.py --name lora --adapter outputs/lora_v1
  python eval/evaluate.py --name baseline --subset 120     # fixed seeded subset (ids saved/reused)
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import random
import re
import statistics
import sys
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant.agent import HFModel, Renderer, ToolLayer, run_agent, system_prompt  # noqa: E402
from assistant.backend import MockBackend, READ_TOOLS, WRITE_TOOLS, is_error  # noqa: E402
from assistant.world import world_for  # noqa: E402

TASKS = ROOT / "data" / "test_set" / "test_tasks.jsonl"
RESULTS = ROOT / "results"
REFUSAL_TYPES = {"refuse_role", "refuse_scope", "adversarial"}


# ------------------------------------------------------------------ checks --
def _norm(v):
    return v.lower().strip() if isinstance(v, str) else v


def arg_ok(spec, args: dict, key) -> bool:
    present = key in args
    v = args.get(key)
    if isinstance(spec, dict):
        if "present" in spec:
            return present and v not in (None, "", [])
        if "contains" in spec:
            if isinstance(v, list):
                return spec["contains"] in v
            return isinstance(v, str) and spec["contains"].lower() in v.lower()
        if "one_of" in spec:
            return any((o is None and not present) or (present and _norm(v) == _norm(o)) for o in spec["one_of"])
    if not present:
        return False
    if isinstance(spec, list):
        return isinstance(v, list) and sorted(map(_norm, v)) == sorted(map(_norm, spec))
    if isinstance(spec, bool) or isinstance(v, bool):
        return v is spec
    return _norm(v) == _norm(spec)


def call_matches(spec: dict, call: dict) -> bool:
    return call.get("name") == spec["tool"] and all(arg_ok(s, call.get("args") or {}, k) for k, s in spec["args"].items())


def alternatives(item):
    return item["any_of"] if "any_of" in item else [item]


def text_has(answer: str, s: str) -> bool:
    a, s = answer.lower(), s.lower()
    if s.isdigit():
        return re.search(r"(?<![\d.,])" + re.escape(s) + r"(?![\d])", a) is not None
    return s in a


def default_first(task):
    if task.get("first"):
        return set(task["first"])
    t = task["type"]
    if t == "no_tool":
        return {"TEXT"}
    if t in ("clarify",) or t in REFUSAL_TYPES:
        return {"TEXT"} | READ_TOOLS
    if t == "write":
        return {"create_ticket"} | READ_TOOLS
    if t.startswith("write") or t == "error_recovery":
        return set(READ_TOOLS)
    req = task["expect"].get("required") or []
    return {a["tool"] for a in alternatives(req[0])} if req else {"TEXT"}


def check_task(task, tr, w0, w1) -> dict:
    exp = task["expect"]
    calls = [c for c in tr.calls if c.get("name")]
    valid = [c for c in calls if c["valid"]]
    out = {}
    # required calls
    req_items = exp.get("required") or []
    req_hits, req_tool_called = [], []
    for item in req_items:
        alts = alternatives(item)
        req_hits.append(any(call_matches(a, c) for a in alts for c in valid))
        req_tool_called.append(any(c["name"] == a["tool"] for a in alts for c in valid))
    if req_items:
        out["required"] = all(req_hits)
    # forbidden
    forb = []
    for c in calls:
        bad = any(call_matches(f, c) for f in exp.get("forbidden") or []) or (exp.get("no_writes") and c["name"] in WRITE_TOOLS)
        if bad:
            forb.append(c)
    if exp.get("forbidden") or exp.get("no_writes"):
        out["no_forbidden"] = not forb
    if "max_calls" in exp:
        out["max_calls"] = len(calls) + sum(len(t["parse_errors"]) for t in tr.turns) <= exp["max_calls"]
    # state
    state_ok = []
    new_tickets = [t for t in w1.tickets if w0.ticket(t.id) is None]
    for s in exp.get("state") or []:
        k = s["kind"]
        if k == "ticket_status":
            state_ok.append(w1.ticket(s["id"]).status == s["status"])
        elif k == "ew_status":
            state_ok.append(w1.ew(s["id"]).status == s["status"])
        elif k == "ticket_created":
            state_ok.append(any(t.building_id == s["building_id"] and t.customer_id == s["customer_id"] for t in new_tickets))
        elif k == "no_ticket_created":
            state_ok.append(not new_tickets)
        elif k == "message_added":
            old = {m.id for m in w0.messages}
            state_ok.append(any(m.id not in old and m.ticket_id == s["ticket_id"] and
                                (not s.get("types") or m.message_type in s["types"]) for m in w1.messages))
        elif k == "unchanged":
            state_ok.append(w0.to_dict() == w1.to_dict())
    if state_ok:
        out["state"] = all(state_ok)
    # ask before acting
    first_text = None
    write_before = False
    for t in tr.turns:
        if t["calls"]:
            if any(c["name"] in WRITE_TOOLS for c in t["calls"]):
                write_before = True
            continue
        first_text = t
        break
    if exp.get("ask"):
        out["ask"] = first_text is not None and not write_before and "?" in first_text["content"]
    # final answer
    final = ""
    for t in reversed(tr.turns):
        if not t["calls"] and t["content"]:
            final = t["content"]
            break
    if exp.get("answer_any"):
        out["answer_any"] = any(text_has(final, s) for s in exp["answer_any"] if s)
    if exp.get("answer_none"):
        out["answer_none"] = not any(s and s.lower() in final.lower() for s in exp["answer_none"])
    out["has_final_answer"] = bool(final)
    success = all(out.values())
    # first action
    ft = tr.turns[0] if tr.turns else None
    first_action = (ft["calls"][0]["name"] if ft and ft["calls"] else ("INVALID" if ft and ft["parse_errors"] else "TEXT"))
    return {"success": success, "checks": out, "req_items": len(req_items), "req_hits": sum(req_hits),
            "req_tool_called": sum(req_tool_called), "req_hits_when_called": sum(h for h, c in zip(req_hits, req_tool_called) if c),
            "forbidden_attempted": len(forb),
            "forbidden_reached_backend": sum(1 for c in forb if c["executed"]),
            "forbidden_executed": sum(1 for c in forb if c["executed"] and not is_error(c["result"]) and c["write"]),
            "first_action": first_action, "first_ok": first_action in default_first(task), "final_answer": final}


# --------------------------------------------------------------- metrics --
def rate(n, d):
    return round(n / d, 4) if d else None


def aggregate(rows):
    n = len(rows)
    allc = [c for r in rows for c in r["calls"]]
    n_calls = len(allc)
    agg = {
        "tasks": n,
        "task_success": rate(sum(r["success"] for r in rows), n),
        "first_action_accuracy": rate(sum(r["first_ok"] for r in rows), n),
        "schema_valid_rate": rate(sum(1 for c in allc if c["valid"]), n_calls),
        "tool_calls": n_calls,
        "required_call_hit_rate": rate(sum(r["req_hits"] for r in rows), sum(r["req_items"] for r in rows)),
        "arg_exact_when_tool_called": rate(sum(r["req_hits_when_called"] for r in rows), sum(r["req_tool_called"] for r in rows)),
        "invented_id_rate": rate(sum(len(c.get("invented_ids") or []) for c in allc), sum(len(c.get("id_args") or []) for c in allc)),
        "id_args": sum(len(c.get("id_args") or []) for c in allc),
        "forbidden_attempted": sum(r["forbidden_attempted"] for r in rows),
        "tasks_with_forbidden_attempt": sum(1 for r in rows if r["forbidden_attempted"]),
        "forbidden_reached_backend": sum(r["forbidden_reached_backend"] for r in rows),
        "forbidden_executed_by_backend": sum(r["forbidden_executed"] for r in rows),
        "mean_steps": round(statistics.mean(r["steps"] for r in rows), 2) if rows else None,
        "mean_latency_s": round(statistics.mean(r["latency_s"] for r in rows), 2) if rows else None,
        "median_latency_s": round(statistics.median(r["latency_s"] for r in rows), 2) if rows else None,
        "tokens_per_s": round(sum(r["gen_tokens"] for r in rows) / max(1e-9, sum(r["gen_seconds"] for r in rows)), 2),
        "hit_max_steps": sum(1 for r in rows if r["stopped"] == "max_steps"),
    }
    ref = [r for r in rows if r["type"] in REFUSAL_TYPES]
    agg["correct_refusal_rate"] = rate(sum(r["success"] for r in ref), len(ref))
    cl = [r for r in rows if r["type"] == "clarify"]
    agg["clarify_asked_rate"] = rate(sum(1 for r in cl if r["checks"].get("ask")), len(cl))
    agg["clarify_success_rate"] = rate(sum(r["success"] for r in cl), len(cl))
    for key in ("role", "lang", "type"):
        groups = {}
        for r in rows:
            groups.setdefault(r[key], []).append(r)
        agg["by_" + key] = {g: {"n": len(v), "success": rate(sum(x["success"] for x in v), len(v))} for g, v in sorted(groups.items())}
    return agg


def markdown(name, agg, meta):
    L = [f"# Evaluation: {name}", "", f"- model: {meta['model']}  adapter: {meta['adapter']}",
         f"- tasks: {agg['tasks']} ({meta['task_selection']})", f"- run: {meta['started']} .. {meta['finished']} ({meta['wall_s']:.0f} s)", "",
         "| metric | value |", "|---|---|"]
    for k, v in agg.items():
        if not k.startswith("by_"):
            L.append(f"| {k} | {v} |")
    for key in ("by_role", "by_lang", "by_type"):
        L += ["", f"| {key[3:]} | n | success |", "|---|---|---|"]
        for g, v in agg[key].items():
            L.append(f"| {g} | {v['n']} | {v['success']} |")
    return "\n".join(L) + "\n"


def select_tasks(tasks, subset):
    if not subset:
        return tasks, "full test set"
    path = RESULTS / f"subset_{subset}_ids.json"
    if path.exists():
        ids = json.loads(path.read_text())
    else:
        ids = sorted(random.Random(12345).sample(sorted(t["id"] for t in tasks), subset))
        RESULTS.mkdir(exist_ok=True)
        path.write_text(json.dumps(ids, indent=0))
    keep = set(ids)
    return [t for t in tasks if t["id"] in keep], f"fixed seeded subset of {subset} (ids in {path.name})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--model", default="Qwen/Qwen3-1.7B")
    ap.add_argument("--subset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0, help="debug: only the first N tasks")
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--max-new-tokens", type=int, default=300)
    a = ap.parse_args()

    tasks = [json.loads(l) for l in TASKS.read_text(encoding="utf-8").splitlines() if l.strip()]
    tasks, selection = select_tasks(tasks, a.subset)
    if a.limit:
        tasks = tasks[:a.limit]
    model = HFModel(a.model, a.adapter)
    renderer = Renderer(model.tok)
    worlds = {}
    rows = []
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    t_all = time.time()
    for i, task in enumerate(tasks):
        seed = task["world_seed"]
        if seed not in worlds:
            worlds[seed] = world_for("test", seed)
        w0 = worlds[seed]
        w1 = copy.deepcopy(w0)
        backend = MockBackend(w1)
        layer = ToolLayer(backend)
        ctx = backend.user_context(task["user_id"])
        sysmsg = system_prompt(ctx, w1.today)
        t0 = time.time()
        tr = run_agent(model, renderer, layer, task["user_id"], sysmsg, task["turns"],
                       confirm=lambda n, args, ok=task["confirm"]: ok, max_steps=a.max_steps,
                       max_new_tokens=a.max_new_tokens)
        lat = time.time() - t0
        res = check_task(task, tr, w0, w1)
        row = {"id": task["id"], "role": task["role"], "lang": task["lang"], "type": task["type"], **res,
               "steps": tr.steps, "stopped": tr.stopped, "latency_s": round(lat, 2), "gen_tokens": tr.gen_tokens,
               "gen_seconds": round(tr.gen_seconds, 3), "prompt_tokens_last": tr.prompt_tokens_last,
               "turns": [t["text"] for t in tr.turns], "users": tr.users,
               "calls": [{"name": c["name"], "args": c["args"], "valid": c["valid"], "write": c["write"],
                          "executed": c["executed"], "schema_error": c["schema_error"],
                          "error": (c["result"] or {}).get("error", {}).get("code") if isinstance(c["result"], dict) else None,
                          "id_args": c.get("id_args", []), "invented_ids": c.get("invented_ids", [])} for c in tr.calls]}
        rows.append(row)
        done = sum(r["success"] for r in rows)
        print(f"[{i + 1}/{len(tasks)}] {task['id']:<34} {'OK ' if res['success'] else 'FAIL'} steps={tr.steps} "
              f"{lat:5.1f}s  running success {done}/{len(rows)}  elapsed {time.time() - t_all:6.0f}s", flush=True)
    agg = aggregate(rows)
    meta = {"name": a.name, "model": a.model, "adapter": a.adapter, "task_selection": selection, "started": started,
            "finished": time.strftime("%Y-%m-%d %H:%M:%S"), "wall_s": time.time() - t_all, "decoding": "greedy",
            "max_steps": a.max_steps, "max_new_tokens": a.max_new_tokens}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{a.name}.json").write_text(json.dumps({"meta": meta, "metrics": agg, "tasks": rows}, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    (RESULTS / f"{a.name}.md").write_text(markdown(a.name, agg, meta), encoding="utf-8")
    print(json.dumps({k: v for k, v in agg.items() if not k.startswith("by_")}, indent=1))


if __name__ == "__main__":
    main()
