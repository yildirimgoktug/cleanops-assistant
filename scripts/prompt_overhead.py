"""Measure the prompt overhead of the tool definitions and of the full first prompt per role.

  python scripts/prompt_overhead.py        -> results/prompt_overhead.json

Tool overhead = tokens of the chat template with the role's tools minus without tools. The full first
prompt is measured with the real system prompt of every persona in test world 1 (mean per role).
"""
import json
import os
import pathlib
import statistics
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from transformers import AutoTokenizer  # noqa: E402

from assistant.agent import Renderer, load_tools, prompt_tools, system_prompt  # noqa: E402
from assistant.backend import MockBackend  # noqa: E402
from assistant.world import ALL_ROLES, world_for  # noqa: E402


def main():
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-1.7B")
    spec = load_tools()
    r = Renderer(tok)

    def overhead(tools):
        return len(r.prefix("s", "u", tools)) - len(r.prefix("s", "u", []))

    w = world_for("test", 1)
    b = MockBackend(w)
    out = {"v1_all_roles_tool_tokens": overhead(prompt_tools(spec)), "per_role": {}}
    for role in ALL_ROLES:
        us = [u for u in w.users if u.role == role]
        v1 = [len(r.prefix(system_prompt(b.user_context(u.id), w.today, hardened=False), "x", prompt_tools(spec))) for u in us]
        v2 = [len(r.prefix(system_prompt(b.user_context(u.id), w.today), "x", prompt_tools(spec, role))) for u in us]
        out["per_role"][role] = {"tools": len(prompt_tools(spec, role)), "tool_tokens": overhead(prompt_tools(spec, role)),
                                 "first_prompt_v1_mean": round(statistics.mean(v1)),
                                 "first_prompt_hardened_mean": round(statistics.mean(v2))}
    (ROOT / "results" / "prompt_overhead.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
