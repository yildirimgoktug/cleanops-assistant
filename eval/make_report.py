"""Build results/summary.md from the result files and paste it into README.md between the
<!-- RESULTS:START --> and <!-- RESULTS:END --> markers. Every number comes from a file a run wrote;
files that do not exist (yet) are left out.

  python eval/make_report.py
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ROOT / "results"

# (result file, column name) on the fixed 120-task subset
SUBSET_RUNS = [("baseline.json", "baseline"), ("lora.json", "v1"), ("v1_hardened.json", "v1-hardened"), ("v2.json", "v2")]
INJECTION_RUNS = [("injection_v1_legacy.json", "v1 (v1 setup)"), ("injection_v1.json", "v1-hardened"), ("injection_v2.json", "v2")]
REST_RUNS = [("v2_rest179.json", "v2")]
COMPARISONS = [("comparison.md", "baseline -> v1"), ("comparison_v1_v1hardened.md", "v1 -> v1-hardened (code changes only)"),
               ("comparison_v1_v2.md", "v1 -> v2"), ("comparison_v1hardened_v2.md", "v1-hardened -> v2 (retraining only)")]

ROWS = [("task_success", "Task success"), ("first_action_accuracy", "First action acceptable"),
        ("schema_valid_rate", "Tool calls schema-valid"), ("required_call_hit_rate", "Required calls made with right args"),
        ("arg_exact_when_tool_called", "Arg exact match, when the required tool was called"),
        ("invented_id_rate", "Invented-id rate (id args never seen in context)"),
        ("forbidden_attempted", "Forbidden calls attempted"), ("tasks_with_forbidden_attempt", "Tasks with a forbidden attempt"),
        ("forbidden_blocked_by_tool_layer", "Forbidden calls blocked by the tool layer"),
        ("forbidden_reached_backend", "Forbidden calls that reached the backend"),
        ("forbidden_executed_by_backend", "Forbidden writes the backend executed"),
        ("correct_refusal_rate", "Correct refusal (refuse/adversarial tasks)"),
        ("clarify_asked_rate", "Asked when a detail was missing (clarify tasks)"),
        ("clarify_success_rate", "Clarify tasks fully solved"), ("mean_steps", "Mean model turns per task"),
        ("mean_latency_s", "Mean latency per task (s)"), ("median_latency_s", "Median latency per task (s)"),
        ("tokens_per_s", "Generation speed (tokens/s)"), ("tool_calls", "Tool calls emitted"),
        ("calls_blocked_by_tool_layer", "All calls blocked by the tool layer"),
        ("hit_max_steps", "Tasks that hit the 8-turn limit")]

INJ_ROWS = [("tasks", "Tasks"), ("user_task_success", "User's own request done, attack not followed"),
            ("attack_attempted_tasks", "Tasks where the model attempted the attack"),
            ("attack_calls", "Attack tool calls emitted"),
            ("attack_calls_blocked_by_tool_layer", "Attack calls blocked by the tool layer"),
            ("attack_calls_reached_backend", "Attack calls that reached the backend"),
            ("attack_executed_tasks", "Tasks where an attack call was executed (write done or foreign data returned)"),
            ("followed_in_text_tasks", "Tasks where an injected text instruction was followed"),
            ("leaked_in_text_tasks", "Tasks where another tenant's data appeared in the answer"),
            ("attack_succeeded_tasks", "Tasks where the attack succeeded (any of the three above)"),
            ("backend_would_allow_tasks", "Tasks where the backend would accept the attack call"),
            ("attack_succeeded_where_backend_would_allow", "... of which the attack succeeded")]


def fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float) and 0 <= v <= 1.0:
        return f"{v:.3f}"
    return str(v)


def load(name):
    p = R / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def table(runs, rows, getter):
    names = [n for _f, n, _d in runs]
    L = ["| Metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for k, label in rows:
        L.append(f"| {label} | " + " | ".join(fmt(getter(d, k)) for _f, _n, d in runs) + " |")
    return L


def main():
    L = []
    sub = [(f, n, d) for f, n in SUBSET_RUNS if (d := load(f))]
    if sub:
        d0 = sub[0][2]
        L += [f"**Fixed 120-task subset** ({d0['meta']['task_selection']}); greedy decoding; at most "
              f"{d0['meta']['max_steps']} model turns per task. baseline and v1 ran in the v1 setup (all 16 tools, no data "
              "blocks, no write id check or cap); v1-hardened is the same v1 adapter with this round's code changes; v2 is "
              "the retrained adapter with the same code.", ""]
        L += table(sub, ROWS, lambda d, k: d["metrics"].get(k))
        for key, title in (("by_role", "role"), ("by_lang", "language"), ("by_type", "task type")):
            names = [n for _f, n, _d in sub]
            L += ["", f"Task success by {title}:", "", f"| {title} | n | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
            for g, v in d0["metrics"][key].items():
                L.append(f"| {g} | {v['n']} | " + " | ".join(fmt(d["metrics"][key].get(g, {}).get("success")) for _f, _n, d in sub) + " |")
    inj = [(f, n, d) for f, n in INJECTION_RUNS if (d := load(f))]
    if inj:
        L += ["", f"**Prompt-injection set** ({inj[0][2]['metrics']['tasks']} tasks, data/test_set/injection_tasks.jsonl). "
              "The scripted user confirms every write dialog (worst case), so 'executed' means the change would have happened "
              "for a user who clicks OK without reading.", ""]
        L += table(inj, INJ_ROWS, lambda d, k: d["metrics"]["injection"].get(k))
        vectors = list(inj[-1][2]["metrics"]["injection_by_vector"])
        L += ["", "Attack succeeded / tasks, by vector:", "", "| vector | " + " | ".join(n for _f, n, _d in inj) + " |",
              "|---|" + "---|" * len(inj)]
        for v in vectors:
            L.append(f"| {v} | " + " | ".join(
                f"{d['metrics']['injection_by_vector'][v]['attack_succeeded_tasks']}/{d['metrics']['injection_by_vector'][v]['tasks']}"
                for _f, _n, d in inj) + " |")
    rest = [(f, n, d) for f, n in REST_RUNS if (d := load(f))]
    if rest:
        d = rest[0][2]
        L += ["", f"**The other {d['metrics']['tasks']} test tasks** ({d['meta']['task_selection']}), never evaluated before this "
              "run and not looked at while designing v2. This is the cleanest number for v2.", ""]
        L += table(rest, ROWS, lambda d, k: d["metrics"].get(k))
        L += ["", "Task success by task type:", "", "| task type | n | v2 |", "|---|---|---|"]
        for g, v in d["metrics"]["by_type"].items():
            L.append(f"| {g} | {v['n']} | {fmt(v['success'])} |")
    for fname, title in COMPARISONS:
        p = R / fname
        if p.exists():
            block = p.read_text(encoding="utf-8").split("## Metrics side by side")[0].split("\n", 2)[2].strip()
            L += ["", f"Paired comparison {title}:", "", block]
    po = load("prompt_overhead.json")
    if po:
        L += ["", "Prompt size (tokens, test world 1):", "", "| role | tools | tool tokens (v1: all 16 = "
              f"{po['v1_all_roles_tool_tokens']}) | first prompt v1 | first prompt hardened |", "|---|---|---|---|---|"]
        for role, v in po["per_role"].items():
            L.append(f"| {role} | {v['tools']} | {v['tool_tokens']} | {v['first_prompt_v1_mean']} | {v['first_prompt_hardened_mean']} |")
    for fname, title in (("train_summary.json", "v1"), ("train_summary_v2.json", "v2")):
        t = load(fname)
        if not t:
            continue
        L += ["", f"Training run {title}:", "",
              f"- {t['optimizer_steps']} optimizer steps x batch 1 x grad-accum {t['grad_accum']} = {t['examples_seen']} "
              f"conversations seen, out of {t['train_examples_available']} ({t['epochs']} epochs)",
              f"- wall clock {t['wall_clock_s']} s over {t.get('segments', 1)} segment(s) (training loop of the last segment "
              f"{t['train_runtime_s']} s), probe speed {t['s_per_step_probe']} s/step, peak VRAM {t['peak_vram_gib']} GiB",
              f"- train loss (logged, assistant tokens) first {t['first_train_loss']} -> last {t['final_train_loss']}; "
              f"val loss on a fixed {t['val_subset_n']}-conversation subset: "
              + ", ".join(f"step {e['step']}: {e['eval_loss']:.4f}" for e in t["eval_history"])]
    text = "\n".join(L) + "\n"
    (R / "summary.md").write_text("# Results summary (generated by eval/make_report.py)\n\n" + text, encoding="utf-8")
    readme = ROOT / "README.md"
    s = readme.read_text(encoding="utf-8")
    if "<!-- RESULTS:START -->" in s:
        pre, rest_ = s.split("<!-- RESULTS:START -->", 1)
        post = rest_.split("<!-- RESULTS:END -->", 1)[1]
        readme.write_text(pre + "<!-- RESULTS:START -->\n" + text + "<!-- RESULTS:END -->" + post, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
