"""Agent loop: system prompt, Qwen3 chat rendering, tool-call parsing, validation, execution.

Design choices (documented in the README):

* Native Qwen3 tool format. The first prompt (system + tools + first user
  message) is rendered with the tokenizer's chat template, `tools=` and
  `enable_thinking=False`. Later turns are appended as token ids, using the
  same strings the template produces for tool responses and user messages,
  and every new assistant turn starts with the empty think block that
  `enable_thinking=False` puts in a generation prompt. Training sequences are
  built with exactly the same function, so training and inference see the
  same tokens.
* Confirmation of writes is done by the tool layer, not by the model. When
  the model emits a write call, the app shows it to the user; only after the
  user confirms is it executed. If the user declines, the model receives a
  "cancelled" result. The model is told this in the system prompt and never
  asks "shall I?" itself. In offline evaluation a scripted user answers.
* The tool layer validates every call against the JSON schema before it
  reaches the backend, and trims results (at most 5 list items, empty search
  groups dropped, compact JSON) so transcripts stay short.
"""
from __future__ import annotations

import copy
import json
import pathlib
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import jsonschema

from .backend import Backend, WRITE_TOOLS, is_error
from .world import ROLE_LABEL

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS_PATH = ROOT / "tools" / "tools_v1.json"

# Parameters that exist in the schema and the backend but are not advertised to the model in v1,
# to keep the prompt short (the 16 tool definitions alone cost ~2,300 tokens).
PROMPT_DROP = {"page", "page_size", "ordering", "archived", "request_intent", "routing_decision",
               "deadline_before", "deadline_after", "lifecycle", "awaiting_customer_approval_days"}
# Parameter descriptions kept in the prompt (they carry rules); the others are dropped to save tokens.
PROMPT_KEEP_DESC = {"message_type", "note", "override_reason", "reason", "my_jobs", "my_managed", "agenda", "customer_id",
                    "ticket_id", "invoice_id", "status"}
MAX_LIST_ITEMS = 5

IM_END = "<|im_end|>"
GEN_PREFIX = "<|im_start|>assistant\n<think>\n\n</think>\n\n"


def load_tools(path=TOOLS_PATH) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def prompt_tools(spec: Optional[dict] = None) -> list:
    """The tool definitions as they are passed to the chat template (`tools=`)."""
    spec = spec or load_tools()
    out = []
    for t in spec["tools"]:
        p = copy.deepcopy(t["parameters"])
        for k in list(p["properties"]):
            if k in PROMPT_DROP:
                del p["properties"][k]
                continue
            for lim in ("minimum", "maximum", "minLength", "maxLength"):
                p["properties"][k].pop(lim, None)
            if k not in PROMPT_KEEP_DESC:
                p["properties"][k].pop("description", None)
        p.pop("additionalProperties", None)
        out.append({"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": p}})
    return out


def system_prompt(ctx: dict, today: str) -> str:
    role = ROLE_LABEL[ctx["role"]]
    lines = [f"You are the CleanOps assistant of a facility-services platform. Today is {today}.",
             f"Signed-in user: {ctx['name']} (user id {ctx['user_id']}), role: {role}."]
    if ctx["role"] == "SUPER_ADMIN":
        lines.append("Scope: all companies.")
    if "company" in ctx:
        lines.append(f"Company: {ctx['company']['name']} (id {ctx['company']['id']}).")
    if "customer" in ctx:
        lines.append(f"Customer organisation: {ctx['customer']['name']} (id {ctx['customer']['id']}).")
    if ctx.get("buildings"):
        label = "Buildings you manage" if ctx["role"] == "BUILDING_MANAGER" else "Your buildings"
        lines.append(label + ": " + "; ".join(f"{b['name']} (id {b['id']})" for b in ctx["buildings"]) + ".")
    lines += [
        "Rules:",
        "- Work only through the tools. They run with this user's own rights, so you only see what the user may see.",
        "- Never invent ids. Take ids from this prompt, the user's message or earlier tool results; use search_records or a list tool to find them.",
        "- Look before you change: read a ticket before changing its status and only use a status from its allowed_next_statuses; read an extra-work request before deciding on it.",
        "- Write tools (create_ticket, add_ticket_message, change_ticket_status, decide_extra_work) are shown to the user by the app for confirmation; do not ask for confirmation yourself. If a required detail is missing or unclear, ask one short question instead of guessing.",
        "- If the request is outside this user's rights, do not call a write tool; say politely that their role cannot do this and who can. If something is not found, say so; do not guess.",
        "- Reply briefly, in the user's language (Dutch or English).",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool layer
# ---------------------------------------------------------------------------
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ToolLayer:
    """Validates, confirms (for writes), executes and trims tool calls."""

    def __init__(self, backend: Backend, spec: Optional[dict] = None):
        self.backend = backend
        self.spec = spec or load_tools()
        self.schemas = {t["name"]: t["parameters"] for t in self.spec["tools"]}

    def validate(self, name: str, args) -> Optional[str]:
        if name not in self.schemas:
            return f"unknown tool '{name}'"
        if not isinstance(args, dict):
            return "arguments must be a JSON object"
        try:
            jsonschema.validate(args, self.schemas[name])
        except jsonschema.ValidationError as e:
            return e.message
        props = self.schemas[name]["properties"]
        for k, v in args.items():
            if props.get(k, {}).get("format") == "date" and not (isinstance(v, str) and _DATE.match(v)):
                return f"{k} must be a date YYYY-MM-DD"
        return None

    def execute(self, user_id: int, name: str, args: dict, confirm: Optional[Callable] = None) -> dict:
        """Returns a record: {name, args, valid, error, confirmed, executed, result}."""
        rec = {"name": name, "args": args, "valid": True, "schema_error": None, "write": name in WRITE_TOOLS,
               "confirmed": None, "executed": False, "result": None}
        problem = self.validate(name, args)
        if problem:
            rec.update(valid=False, schema_error=problem,
                       result={"error": {"status": 400, "code": "invalid_arguments", "detail": problem}})
            return rec
        if name in WRITE_TOOLS:
            ok = True if confirm is None else bool(confirm(name, args))
            rec["confirmed"] = ok
            if not ok:
                rec["result"] = {"status": "cancelled", "detail": "The user did not confirm. Nothing was changed."}
                return rec
        rec["result"] = self.backend.call(user_id, name, args)
        rec["executed"] = True
        return rec


def compact(name: str, result: dict) -> dict:
    """Trim a backend result for the model's context (same trimming in training and inference)."""
    if not isinstance(result, dict) or is_error(result):
        return result
    r = copy.deepcopy(result)
    if "results" in r and isinstance(r["results"], list):
        if len(r["results"]) > MAX_LIST_ITEMS:
            r["results"] = r["results"][:MAX_LIST_ITEMS]
            r["showing"] = MAX_LIST_ITEMS
    if name == "search_records":
        r["groups"] = {k: v for k, v in r["groups"].items() if v}
        if not r.get("truncated"):
            r.pop("truncated", None)
    return r


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Rendering (shared by training and inference)
# ---------------------------------------------------------------------------
def assistant_text(content: str = "", tool_calls: Optional[list] = None) -> str:
    """Assistant turn text exactly as the Qwen3 template renders it (after the think block)."""
    s = content or ""
    for i, c in enumerate(tool_calls or []):
        if (i == 0 and s) or i > 0:
            s += "\n"
        s += '<tool_call>\n{"name": "' + c["name"] + '", "arguments": ' + json.dumps(c["arguments"], ensure_ascii=False) + "}\n</tool_call>"
    return s


def tool_block(contents: list) -> str:
    s = "\n<|im_start|>user"
    for c in contents:
        s += "\n<tool_response>\n" + c + "\n</tool_response>"
    return s + IM_END + "\n" + GEN_PREFIX


def user_block(text: str) -> str:
    return "\n<|im_start|>user\n" + text + IM_END + "\n" + GEN_PREFIX


class Renderer:
    def __init__(self, tokenizer, tools: Optional[list] = None):
        self.tok = tokenizer
        self.tools = tools if tools is not None else prompt_tools()
        self.im_end = tokenizer.convert_tokens_to_ids(IM_END)

    def enc(self, s: str) -> list:
        return self.tok(s, add_special_tokens=False)["input_ids"]

    def prefix(self, system: str, user: str) -> list:
        ids = self.tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                           tools=self.tools, add_generation_prompt=True, enable_thinking=False,
                                           tokenize=True)
        if isinstance(ids, dict):
            ids = ids["input_ids"]
        return list(ids)

    def encode_conversation(self, messages: list):
        """messages in chat format (system, user, assistant[tool_calls], tool, ...). Returns (ids, mask)
        with mask=1 on the tokens the assistant produces (its text, tool calls and <|im_end|>)."""
        assert messages[0]["role"] == "system" and messages[1]["role"] == "user"
        ids = self.prefix(messages[0]["content"], messages[1]["content"])
        mask = [0] * len(ids)
        i = 2
        while i < len(messages):
            m = messages[i]
            if m["role"] == "assistant":
                calls = [{"name": c["function"]["name"], "arguments": c["function"]["arguments"]}
                         for c in m.get("tool_calls") or []]
                a = self.enc(assistant_text(m.get("content") or "", calls)) + [self.im_end]
                ids += a
                mask += [1] * len(a)
                i += 1
            elif m["role"] == "tool":
                block = []
                while i < len(messages) and messages[i]["role"] == "tool":
                    block.append(messages[i]["content"])
                    i += 1
                t = self.enc(tool_block(block))
                ids += t
                mask += [0] * len(t)
            elif m["role"] == "user":
                t = self.enc(user_block(m["content"]))
                ids += t
                mask += [0] * len(t)
                i += 1
            else:
                raise ValueError(m["role"])
        return ids, mask


# ---------------------------------------------------------------------------
# Parsing model output
# ---------------------------------------------------------------------------
_CALL = re.compile(r"<tool_call>\s*(.*?)\s*(?:</tool_call>|$)", re.S)


def parse_output(text: str):
    """Returns (content, calls, errors). calls = [{name, arguments}], errors = [raw strings that did not parse]."""
    text = text.replace(IM_END, "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    calls, errors = [], []
    for raw in _CALL.findall(text):
        try:
            obj = json.loads(raw)
            args = obj.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)
            if not isinstance(obj.get("name"), str):
                raise ValueError("no name")
            calls.append({"name": obj["name"], "arguments": args})
        except Exception:
            errors.append(raw)
    content = _CALL.sub("", text).strip()
    return content, calls, errors


# ---------------------------------------------------------------------------
# Model runner + loop
# ---------------------------------------------------------------------------
class HFModel:
    """Greedy generation with a local HF model (optionally with a LoRA adapter)."""

    def __init__(self, model_name="Qwen/Qwen3-1.7B", adapter: Optional[str] = None, device="cuda"):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForCausalLM.from_pretrained(model_name, dtype=torch.bfloat16).to(device)
        if adapter:
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, adapter)
        model.eval()
        self.model = model
        self.device = device
        self.eos = [self.tok.convert_tokens_to_ids(IM_END), self.tok.eos_token_id]

    def generate(self, ids: list, max_new_tokens: int = 300):
        torch = self.torch
        x = torch.tensor([ids], device=self.device)
        torch.cuda.synchronize()
        t0 = time.time()
        with torch.no_grad():
            out = self.model.generate(x, attention_mask=torch.ones_like(x), max_new_tokens=max_new_tokens,
                                      do_sample=False, temperature=None, top_p=None, top_k=None,
                                      eos_token_id=self.eos, pad_token_id=self.tok.eos_token_id)
        torch.cuda.synchronize()
        new = out[0, len(ids):].tolist()
        return new, time.time() - t0


def id_check(args, seen: str):
    """Integer arguments named *_id whose value never appeared in the context so far count as invented."""
    id_args, invented = [], []
    if isinstance(args, dict):
        for k, v in args.items():
            if k.endswith("_id") and isinstance(v, int) and not isinstance(v, bool):
                id_args.append(v)
                if not re.search(r"(?<!\d)" + str(v) + r"(?!\d)", seen):
                    invented.append(v)
    return id_args, invented


@dataclass
class RunTrace:
    turns: list = field(default_factory=list)      # assistant turns: {text, content, calls, parse_errors}
    calls: list = field(default_factory=list)      # ToolLayer records, in order
    users: list = field(default_factory=list)      # user messages sent
    gen_tokens: int = 0
    gen_seconds: float = 0.0
    steps: int = 0
    stopped: str = ""
    prompt_tokens_last: int = 0


def run_agent(model: HFModel, renderer: Renderer, layer: ToolLayer, user_id: int, system: str, user_turns: list,
              confirm: Optional[Callable] = None, max_steps: int = 8, max_new_tokens: int = 300) -> RunTrace:
    tr = RunTrace()
    pending = list(user_turns)
    first = pending.pop(0)
    tr.users.append(first)
    ids = renderer.prefix(system, first)
    seen = system + "\n" + first   # everything the model has been shown, to detect invented ids
    for _ in range(max_steps):
        new, secs = model.generate(ids, max_new_tokens)
        tr.steps += 1
        tr.gen_tokens += len(new)
        tr.gen_seconds += secs
        if not new or new[-1] not in model.eos:
            new = new + [renderer.im_end]  # cut off: close the turn
        elif new[-1] != renderer.im_end:
            new[-1] = renderer.im_end
        ids = ids + new
        text = model.tok.decode(new, skip_special_tokens=False)
        content, calls, errors = parse_output(text)
        tr.turns.append({"text": text.replace(IM_END, ""), "content": content, "calls": calls, "parse_errors": errors})
        if calls or errors:
            results = []
            for c in calls:
                rec = layer.execute(user_id, c["name"], c["arguments"], confirm)
                rec["id_args"], rec["invented_ids"] = id_check(c["arguments"], seen)
                tr.calls.append(rec)
                results.append(dump(compact(c["name"], rec["result"])))
            for _e in errors:
                tr.calls.append({"name": None, "args": None, "valid": False, "schema_error": "unparseable tool call",
                                 "write": False, "confirmed": None, "executed": False, "result": None})
                results.append(dump({"error": {"status": 400, "code": "invalid_tool_call",
                                               "detail": "The tool call was not valid JSON."}}))
            ids = ids + renderer.enc(tool_block(results))
            seen += "\n" + "\n".join(results)
            continue
        if pending:
            nxt = pending.pop(0)
            tr.users.append(nxt)
            seen += "\n" + nxt
            ids = ids + renderer.enc(user_block(nxt))
            continue
        tr.stopped = "final_answer"
        break
    else:
        tr.stopped = "max_steps"
    tr.prompt_tokens_last = len(ids)
    return tr
