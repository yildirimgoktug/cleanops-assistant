"""Paired comparison of two evaluation result files on the same tasks.

  python eval/compare.py results/baseline.json results/lora.json --out results/comparison.md

Lists the tasks whose success flipped and gives an exact McNemar test (two-sided binomial test on
the discordant pairs) for task success.
"""
import argparse
import json
import math
import pathlib


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    A = json.loads(pathlib.Path(args.a).read_text(encoding="utf-8"))
    B = json.loads(pathlib.Path(args.b).read_text(encoding="utf-8"))
    ra = {t["id"]: t for t in A["tasks"]}
    rb = {t["id"]: t for t in B["tasks"]}
    common = sorted(set(ra) & set(rb))
    both = sum(1 for i in common if ra[i]["success"] and rb[i]["success"])
    neither = sum(1 for i in common if not ra[i]["success"] and not rb[i]["success"])
    gained = [i for i in common if not ra[i]["success"] and rb[i]["success"]]
    lost = [i for i in common if ra[i]["success"] and not rb[i]["success"]]
    p = mcnemar_exact(len(gained), len(lost))
    na, nb = A["meta"]["name"], B["meta"]["name"]
    L = [f"# Paired comparison: {na} vs {nb}", "",
         f"Tasks in both files: {len(common)}", "",
         f"| | {nb} success | {nb} fail |", "|---|---|---|",
         f"| **{na} success** | {both} | {len(lost)} |",
         f"| **{na} fail** | {len(gained)} | {neither} |", "",
         f"- {na} success: {both + len(lost)}/{len(common)}; {nb} success: {both + len(gained)}/{len(common)}",
         f"- flipped fail -> success: {len(gained)}; success -> fail: {len(lost)}",
         f"- exact McNemar p (two-sided) = {p:.3g}", "",
         "## Metrics side by side", "", f"| metric | {na} | {nb} |", "|---|---|---|"]
    for k, v in A["metrics"].items():
        if not k.startswith("by_"):
            L.append(f"| {k} | {v} | {B['metrics'].get(k)} |")
    for key in ("by_role", "by_lang", "by_type"):
        L += ["", f"| {key[3:]} | n | {na} | {nb} |", "|---|---|---|---|"]
        for g in A["metrics"][key]:
            L.append(f"| {g} | {A['metrics'][key][g]['n']} | {A['metrics'][key][g]['success']} | "
                     f"{B['metrics'][key].get(g, {}).get('success')} |")
    L += ["", "## Flipped fail -> success", ""] + [f"- {i} ({ra[i]['type']})" for i in gained]
    L += ["", "## Flipped success -> fail", ""] + [f"- {i} ({ra[i]['type']})" for i in lost]
    text = "\n".join(L) + "\n"
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
