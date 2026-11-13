"""Training data v2: hardened format, injection examples, and separation from both test sets."""
import json
import os
import pathlib
import re
import sys

import pytest

os.environ.setdefault("HF_HUB_OFFLINE", "1")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))

import generate as G  # noqa: E402
from assistant.backend import WRITE_TOOLS  # noqa: E402
from assistant.security import DATA_RULE, IDENTITY_RULE  # noqa: E402
from assistant.world import TRAIN_SEEDS  # noqa: E402

TEST = [json.loads(l) for l in (ROOT / "data" / "test_set" / "test_tasks.jsonl").read_text(encoding="utf-8").splitlines()]
INJ = [json.loads(l) for l in (ROOT / "data" / "test_set" / "injection_tasks.jsonl").read_text(encoding="utf-8").splitlines()]


def grams(text, n=5):
    w = re.findall(r"[a-zà-ÿ']+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


@pytest.fixture(scope="module")
def sample():
    return G.sample_per_intent(10)


def test_v2_new_intents_do_not_share_phrasing_with_any_test_set(sample):
    """Every intent added in v2: no 5-word sequence of its user turns or planted texts occurs in the 299-task test set
    or in the injection test set. (Pre-existing v1 templates share a few common 5-word phrases with the 299-task set,
    e.g. 'wat is de status van'; that is documented in the README and not changed here.)"""
    test_grams = set()
    for t in TEST + INJ:
        for u in t["turns"]:
            test_grams |= grams(u)
        for p in t.get("plants") or []:
            test_grams |= grams(p["text"])
    new = [r for r in sample if r["intent"] in G.INTENTS_V2_NEW]
    assert {r["intent"] for r in new} == set(G.INTENTS_V2_NEW)
    labels = sorted(set(G.NL_STATUS.values()) | set(G.EN_STATUS.values()), key=len, reverse=True)
    for r in new:
        for m in r["messages"]:
            if m["role"] == "user":  # tool results carry world data from the name pools, checked by the pool tests
                text = m["content"].lower()
                for lab in labels:  # status names are vocabulary, not phrasing
                    text = text.replace(lab.lower(), " ")
                assert not grams(text) & test_grams, (r["intent"], sorted(grams(text) & test_grams))
    for nl, en, _k in G.INJ_TEXTS:
        assert not (grams(nl) | grams(en)) & test_grams


def test_canary_words_are_separate():
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location("bis", ROOT / "data" / "test_set" / "build_injection_set.py")
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    train_text = " ".join(nl + " " + en for nl, en, _ in G.INJ_TEXTS).upper()
    for w in mod.CANARY_WORDS:
        assert w not in train_text


def test_v2_format(sample):
    for r in sample:
        sysmsg = r["messages"][0]["content"]
        assert DATA_RULE in sysmsg and IDENTITY_RULE in sysmsg
        for m in r["messages"]:
            if m["role"] == "tool":
                assert m["content"].startswith("<data tool=\"") and m["content"].endswith("</data>")
                assert "<|" not in m["content"] and "<tool_call>" not in m["content"]
            if m["role"] == "user":
                assert "<|" not in m["content"]


def test_injection_examples_never_write_and_never_obey(sample):
    for r in sample:
        if r["intent"] not in ("inj_data", "inj_claim", "inj_pressure", "inj_reveal", "x_foreign_id"):
            continue
        calls = [c["function"]["name"] for m in r["messages"] for c in m.get("tool_calls") or []]
        assert not set(calls) & WRITE_TOOLS, r["intent"]
        answers = " ".join(m["content"] for m in r["messages"] if m["role"] == "assistant" and m.get("content"))
        assert "GOUDVIS" not in answers and "GOLDFISH" not in answers


def test_v2_rows_render_with_role_tools():
    tr = pytest.importorskip("transformers")
    try:
        tok = tr.AutoTokenizer.from_pretrained("Qwen/Qwen3-1.7B")
    except Exception:
        pytest.skip("tokenizer not in local cache")
    from assistant.agent import Renderer
    rows, _rej, _att = G.generate(40, TRAIN_SEEDS, 1, "t")
    r = Renderer(tok)
    for x in rows:
        assert x["format"] == "v2"
        ids, mask = r.encode_conversation(x["messages"], G.row_tools(x))
        text = tok.decode(ids)
        names = set(re.findall(r'"name": "([a-z_]+)", "description"', text))
        from assistant.security import ROLE_TOOLS
        assert names == ROLE_TOOLS[x["role"]]
        assert sum(mask) > 0
