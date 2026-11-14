"""Compare base+adapter with the merged model on the first N test tasks (greedy, same agent loop as the evaluation).
Run once per model and compare the two JSON dumps with --compare:

    python scripts/check_merge.py --run --model Qwen/Qwen3-1.7B --adapter outputs/lora_v2 --dump a.json
    python scripts/check_merge.py --run --model C:/Users/NAD/models/cleanops-assistant-merged --dump b.json
    python scripts/check_merge.py --compare a.json b.json
"""
import argparse, copy, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "eval"))


def run(a):
    from assistant.world import apply_plants, world_for
    from assistant.agent import HFModel, Renderer, ToolLayer, run_agent, system_prompt
    from assistant.backend import MockBackend
    from assistant.security import AuditLog
    tasks = [json.loads(l) for l in pathlib.Path(a.tasks).read_text(encoding="utf-8").splitlines() if l.strip()]
    tasks = tasks[:a.n]
    model = HFModel(a.model, a.adapter)
    renderer = Renderer(model.tok)
    out = []
    for task in tasks:
        w = world_for(task.get("world_family", "test"), task["world_seed"])
        w = apply_plants(copy.deepcopy(w), task.get("plants"))
        backend = MockBackend(w)
        layer = ToolLayer(backend, hardened=True, audit=AuditLog())
        sysmsg = system_prompt(backend.user_context(task["user_id"]), w.today, hardened=True)
        tr = run_agent(model, renderer, layer, task["user_id"], sysmsg, task["turns"],
                       confirm=lambda n, args, ok=task["confirm"]: ok)
        out.append({"id": task["id"], "turns": [t["text"] for t in tr.turns]})
    pathlib.Path(a.dump).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def compare(x, y):
    A = json.loads(pathlib.Path(x).read_text(encoding="utf-8")); B = json.loads(pathlib.Path(y).read_text(encoding="utf-8"))
    same = 0
    for p, q in zip(A, B):
        ok = p["turns"] == q["turns"]
        same += ok
        print(("SAME " if ok else "DIFF ") + p["id"])
        if not ok:
            for i, (s, t) in enumerate(zip(p["turns"], q["turns"])):
                if s != t:
                    print("  turn", i, "\n   A:", s[:300], "\n   B:", t[:300]); break
    print(f"{same}/{len(A)} tasks with identical turns")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true"); ap.add_argument("--compare", nargs=2)
    ap.add_argument("--model"); ap.add_argument("--adapter"); ap.add_argument("--dump")
    ap.add_argument("--tasks", default=str(ROOT / "data/test_set/test_tasks.jsonl")); ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()
    if a.compare: compare(*a.compare)
    else: run(a)
