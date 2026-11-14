"""Markdown table of the GGUF runs next to the published adapter results (reads results/*.json).

  python eval/make_gguf_table.py > results/gguf_summary.md
"""
import json
import pathlib

R = pathlib.Path(__file__).resolve().parents[1] / "results"
SETS = [  # (label, published file, [(variant, file), ...])
    ("120-task subset", "v2", "gguf_{v}"),
    ("other 179 tasks", "v2_rest179", "gguf_{v}_rest179"),
    ("injection set (99)", "injection_v2", "gguf_{v}_injection"),
]
VARIANTS = ["q4_k_m", "q5_k_m", "q8_0", "f16"]


def load(name):
    p = R / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main():
    print("| set | HF bf16 + adapter (published) | " + " | ".join(v.upper() for v in VARIANTS) + " |")
    print("|---|---|" + "---|" * len(VARIANTS))
    for label, pub, pat in SETS:
        row = [label]
        d = load(pub)
        row.append(f"{d['metrics']['task_success']:.3f}" if d else "-")
        for v in VARIANTS:
            d = load(pat.format(v=v))
            row.append(f"{d['metrics']['task_success']:.3f}" if d else "not run")
        print("| " + " | ".join(row) + " |")
    print()
    print("| variant | tokens/s (server decode) | tokens/s (harness, incl. prefill) | TTFT median / mean / p90 (s) | mean latency per task (s) |")
    print("|---|---|---|---|---|")
    d = load("v2")
    if d:
        m = d["metrics"]
        print(f"| HF bf16 + adapter (published) | - | {m['tokens_per_s']} | - | {m['mean_latency_s']} |")
    for v in VARIANTS:
        d = load(f"gguf_{v}")
        if d:
            m, meta = d["metrics"], d["meta"]
            print(f"| {v.upper()} | {meta.get('server_decode_tok_s_mean', '-')} | {m['tokens_per_s']} | "
                  f"{meta.get('ttft_s_median', '-')} / {meta.get('ttft_s_mean', '-')} / {meta.get('ttft_s_p90', '-')} | {m['mean_latency_s']} |")


if __name__ == "__main__":
    main()
