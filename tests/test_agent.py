"""Rendering and parsing tests for the agent loop (tokenizer only, no GPU)."""
import os

import pytest

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from assistant.agent import (Renderer, ToolLayer, parse_output, assistant_text, prompt_tools, compact, dump,
                             system_prompt)
from assistant.backend import MockBackend
from assistant.world import world_for


@pytest.fixture(scope="module")
def tok():
    transformers = pytest.importorskip("transformers")
    try:
        return transformers.AutoTokenizer.from_pretrained("Qwen/Qwen3-1.7B")
    except Exception:
        pytest.skip("tokenizer not in local cache")


def test_rendering_matches_chat_template(tok):
    """Our incremental rendering equals the chat template, except that earlier assistant turns keep the
    empty think block that a generation prompt with enable_thinking=False adds."""
    r = Renderer(tok)
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "Hoeveel open meldingen?"},
            {"role": "assistant", "content": "", "tool_calls": [{"type": "function", "function": {"name": "get_ticket_stats", "arguments": {}}}]},
            {"role": "tool", "name": "get_ticket_stats", "content": '{"open":3}'},
            {"role": "assistant", "content": "Je hebt 3 open meldingen."}]
    ids, mask = r.encode_conversation(msgs)
    ours = tok.decode(ids)
    ref = tok.apply_chat_template(msgs, tools=r.tools, tokenize=False, enable_thinking=False)
    ref = ref.replace("<|im_start|>assistant\n<tool_call>", "<|im_start|>assistant\n<think>\n\n</think>\n\n<tool_call>")
    assert ours == ref.rstrip("\n")
    trained = tok.decode([i for i, m in zip(ids, mask) if m])
    assert trained.count("<|im_end|>") == 2 and "get_ticket_stats" in trained and "Je hebt 3" in trained
    assert "Hoeveel" not in trained


def test_prefix_is_generation_prompt(tok):
    r = Renderer(tok)
    ids = r.prefix("sys", "hoi")
    assert tok.decode(ids).endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")


def test_parse_output():
    txt = assistant_text("", [{"name": "get_ticket", "arguments": {"ticket_id": 12}}])
    content, calls, errors = parse_output(txt + "<|im_end|>")
    assert calls == [{"name": "get_ticket", "arguments": {"ticket_id": 12}}] and not errors and content == ""
    content, calls, errors = parse_output("<tool_call>\n{bad json}\n</tool_call>")
    assert not calls and errors
    content, calls, errors = parse_output("Dat kan ik niet doen.")
    assert content == "Dat kan ik niet doen." and not calls


def test_tool_layer_validates_and_confirms():
    w = world_for("train", 1)
    layer = ToolLayer(MockBackend(w))
    u = w.users[1]
    assert not layer.execute(u.id, "get_ticket", {"ticket_id": "12"})["valid"]
    assert not layer.execute(u.id, "list_tickets", {"status": ["DONE"]})["valid"]
    assert not layer.execute(u.id, "list_tickets", {"date_from": "gisteren"})["valid"]
    assert not layer.execute(u.id, "nope", {})["valid"]
    t = w.tickets[0]
    layer.observe(f'{{"id":{t.id}}}')  # a write may only use an id that was shown earlier
    rec = layer.execute(u.id, "add_ticket_message", {"ticket_id": t.id, "message": "x"}, confirm=lambda n, a: False)
    assert rec["confirmed"] is False and not rec["executed"] and rec["result"]["status"] == "cancelled"


def test_compact_trims_lists():
    w = world_for("train", 1)
    b = MockBackend(w)
    sa = w.users[0]
    res = compact("list_tickets", b.call(sa.id, "list_tickets", {}))
    assert len(res["results"]) == 5 and res["showing"] == 5 and res["count"] > 5
    s = compact("search_records", b.call(sa.id, "search_records", {"q": w.tickets[0].ticket_no}))
    assert list(s["groups"]) == ["tickets"]


def test_prompt_tools_cover_all_tools():
    names = [t["function"]["name"] for t in prompt_tools()]
    assert len(names) == 16 and len(set(names)) == 16


def test_system_prompt_mentions_scope():
    w = world_for("train", 1)
    b = MockBackend(w)
    cu = next(u for u in w.users if u.role == "CUSTOMER_USER")
    sp = system_prompt(b.user_context(cu.id), w.today)
    assert w.customer(cu.customer_id).name in sp and "customer user" in sp
