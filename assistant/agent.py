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

from .backend import ALL_TOOLS, Backend, WRITE_TOOLS, is_error
from .security import (AuditLog, DATA_RULE, IDENTITY_RULE, MAX_WRITES_PER_CONVERSATION, ROLE_TOOLS, neutralise,
                       neutralise_obj, role_tool_spec, unseen_ids, wrap_data)
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


def prompt_tools(spec: Optional[dict] = None, role: Optional[str] = None) -> list:
    """The tool definitions as they are passed to the chat template (`tools=`).
    With a role: only that role's tools, narrowed to the role (hardened mode); without: all 16 (v1)."""
    spec = spec or load_tools()
    out = []
    for t in (spec["tools"] if role is None else role_tool_spec(spec, role)):
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


def system_prompt(ctx: dict, today: str, hardened: bool = True) -> str:
    """hardened=False reproduces the v1 prompt; hardened=True neutralises names and adds the data/identity rules."""
    if hardened:
        ctx = neutralise_obj(ctx)
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
    ]
    if hardened:
        lines += [DATA_RULE, IDENTITY_RULE]
    lines.append("- Reply briefly, in the user's language (Dutch or English).")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool layer
# ---------------------------------------------------------------------------
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ToolLayer:
    """Validates, confirms (for writes), executes and trims tool calls, as the signed-in user.

    hardened=True (default) adds the structural controls of assistant/security.py, in this order:
    role tool list -> role-narrowed JSON schema -> (writes) ids must have appeared earlier in the
    conversation -> (writes) per-conversation cap -> (writes) user confirmation -> backend. Every call
    gets an audit line. hardened=False reproduces v1 (full schema, no id check, no cap, no wrapping).
    """

    def __init__(self, backend: Backend, spec: Optional[dict] = None, hardened: bool = True,
                 audit: Optional[AuditLog] = None, max_writes: int = MAX_WRITES_PER_CONVERSATION):
        self.backend = backend
        self.spec = spec or load_tools()
        self.hardened = hardened
        self.full_schemas = {t["name"]: t["parameters"] for t in self.spec["tools"]}
        self.schemas = self.full_schemas
        self.audit = audit if audit is not None else AuditLog()
        self.max_writes = max_writes
        self.writes = 0
        self.seen = ""
        self._role = {}

    # context -----------------------------------------------------------
    def role_of(self, user_id: int) -> str:
        if user_id not in self._role:
            self._role[user_id] = self.backend.user_context(user_id)["role"]
        return self._role[user_id]

    def schemas_for(self, user_id: int) -> dict:
        if not self.hardened:
            return self.full_schemas
        return {t["name"]: t["parameters"] for t in role_tool_spec(self.spec, self.role_of(user_id))}

    def prompt_tools_for(self, user_id: int) -> list:
        return prompt_tools(self.spec, self.role_of(user_id) if self.hardened else None)

    def observe(self, text: str):
        """Everything the model has been shown (system prompt, user turns, tool results); ids of write calls must occur here."""
        self.seen += "\n" + text

    def clean_user_text(self, text: str) -> str:
        return neutralise(text) if self.hardened else text

    def result_text(self, name, result) -> str:
        """A tool result as it goes into the model's context (same in training and inference)."""
        if not self.hardened:
            return dump(compact(name, result))
        tool = name if name in ALL_TOOLS else "unknown"
        return wrap_data(tool, dump(neutralise_obj(compact(name, result))))

    # validation ----------------------------------------------------------
    def validate(self, name: str, args, schemas: Optional[dict] = None) -> Optional[str]:
        schemas = schemas or self.schemas
        if name not in schemas:
            return f"unknown tool '{name}'"
        if not isinstance(args, dict):
            return "arguments must be a JSON object"
        try:
            jsonschema.validate(args, schemas[name])
        except jsonschema.ValidationError as e:
            return e.message
        props = schemas[name]["properties"]
        for k, v in args.items():
            if props.get(k, {}).get("format") == "date" and not (isinstance(v, str) and _DATE.match(v)):
                return f"{k} must be a date YYYY-MM-DD"
        return None

    @staticmethod
    def _blocked(rec, by, status, code, detail):
        rec.update(blocked_by=by, result={"error": {"status": status, "code": code, "detail": detail}})
        if by in ("schema", "unknown_tool"):
            rec.update(valid=False, schema_error=detail)

    def execute(self, user_id: int, name: str, args: dict, confirm: Optional[Callable] = None) -> dict:
        """Returns a record: {name, args, valid, schema_error, write, blocked_by, confirmed, executed, result}."""
        rec = {"name": name, "args": args, "valid": True, "schema_error": None, "write": name in WRITE_TOOLS,
               "blocked_by": None, "confirmed": None, "executed": False, "result": None}
        self._decide(rec, user_id, name, args, confirm)
        res = rec["result"]
        decision = (f"blocked:{rec['blocked_by']}" if rec["blocked_by"] else
                    "invalid_arguments" if not rec["valid"] else
                    "cancelled_by_user" if rec["confirmed"] is False else
                    f"backend_error:{res['error']['code']}" if is_error(res) else "ok")
        try:
            role = self.role_of(user_id)
        except Exception:
            role = None
        self.audit.write(user_id=user_id, role=role, tool=name, args=args, write=rec["write"], decision=decision)
        return rec

    def _decide(self, rec, user_id, name, args, confirm):
        if not self.hardened:
            problem = self.validate(name, args)
            if problem:
                rec.update(valid=False, schema_error=problem,
                           result={"error": {"status": 400, "code": "invalid_arguments", "detail": problem}})
                return
        else:
            if name not in ALL_TOOLS:
                return self._blocked(rec, "unknown_tool", 400, "unknown_tool", f"unknown tool '{name}'")
            if name not in ROLE_TOOLS[self.role_of(user_id)]:
                return self._blocked(rec, "role_filter", 403, "tool_not_available",
                                     f"The tool {name} is not available for this user's role.")
            problem = self.validate(name, args, self.schemas_for(user_id))
            if problem:
                return self._blocked(rec, "schema", 400, "invalid_arguments", problem)
            if name in WRITE_TOOLS:
                bad = unseen_ids(args, self.seen)
                if bad:
                    return self._blocked(rec, "unseen_id", 400, "unknown_id",
                                         f"Id {bad[0]} did not appear in this conversation; look it up first.")
                if self.writes >= self.max_writes:
                    return self._blocked(rec, "write_cap", 429, "write_limit_reached",
                                         f"At most {self.max_writes} changes per conversation; start a new one.")
        if name in WRITE_TOOLS:
            if self.hardened:
                self.writes += 1  # counted when proposed to the user, confirmed or not
            ok = True if confirm is None else bool(confirm(name, args))
            rec["confirmed"] = ok
            if not ok:
                rec["result"] = {"status": "cancelled", "detail": "The user did not confirm. Nothing was changed."}
                return
        rec["result"] = self.backend.call(user_id, name, args)
        rec["executed"] = True


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

    def prefix(self, system: str, user: str, tools: Optional[list] = None) -> list:
        ids = self.tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                           tools=self.tools if tools is None else tools, add_generation_prompt=True,
                                           enable_thinking=False, tokenize=True)
        if isinstance(ids, dict):
            ids = ids["input_ids"]
        return list(ids)

    def encode_conversation(self, messages: list, tools: Optional[list] = None):
        """messages in chat format (system, user, assistant[tool_calls], tool, ...). Returns (ids, mask)
        with mask=1 on the tokens the assistant produces (its text, tool calls and <|im_end|>)."""
        assert messages[0]["role"] == "system" and messages[1]["role"] == "user"
        ids = self.prefix(messages[0]["content"], messages[1]["content"], tools)
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
        """Greedy decoding with a manual loop: logits only for the last position (the full-sequence logits of a
        3-4k token prefill do not fit next to the model in 6 GB), and the KV cache is reused when the new
        prompt extends the previous one (the agent loop only appends tokens)."""
        torch = self.torch
        from transformers import DynamicCache
        torch.cuda.synchronize()
        t0 = time.time()
        prev = getattr(self, "_cache_ids", None)
        if prev is not None and len(prev) < len(ids) and ids[:len(prev)] == prev:
            cache, start = self._cache, len(prev)
        else:
            cache, start = DynamicCache(), 0
        new = []
        with torch.no_grad():
            for c0 in range(start, len(ids), 1024):  # chunked prefill keeps activation memory bounded
                c1 = min(len(ids), c0 + 1024)
                x = torch.tensor([ids[c0:c1]], device=self.device)
                pos = torch.arange(c0, c1, device=self.device)
                out = self.model(input_ids=x, past_key_values=cache, use_cache=True, cache_position=pos, logits_to_keep=1)
            fed = list(ids)
            for _ in range(max_new_tokens):
                nxt = int(out.logits[0, -1].argmax())
                new.append(nxt)
                if nxt in self.eos:
                    break
                fed.append(nxt)
                p = torch.tensor([len(fed) - 1], device=self.device)
                out = self.model(input_ids=torch.tensor([[nxt]], device=self.device), past_key_values=cache,
                                 use_cache=True, cache_position=p, logits_to_keep=1)
        torch.cuda.synchronize()
        self._cache, self._cache_ids = cache, fed
        return new, time.time() - t0

    def reset(self):
        self._cache, self._cache_ids = None, None


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
    audit: list = field(default_factory=list)


def run_agent(model: HFModel, renderer: Renderer, layer: ToolLayer, user_id: int, system: str, user_turns: list,
              confirm: Optional[Callable] = None, max_steps: int = 8, max_new_tokens: int = 300) -> RunTrace:
    tr = RunTrace()
    if hasattr(model, "reset"):
        model.reset()
    pending = [layer.clean_user_text(u) for u in user_turns]
    first = pending.pop(0)
    tr.users.append(first)
    ids = renderer.prefix(system, first, layer.prompt_tools_for(user_id) if layer.hardened else None)
    seen = system + "\n" + first   # everything the model has been shown, to detect invented ids
    layer.observe(seen)
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
                results.append(layer.result_text(c["name"], rec["result"]))
            for _e in errors:
                tr.calls.append({"name": None, "args": None, "valid": False, "schema_error": "unparseable tool call",
                                 "write": False, "blocked_by": "unparseable", "confirmed": None, "executed": False,
                                 "result": None})
                results.append(layer.result_text("invalid", {"error": {"status": 400, "code": "invalid_tool_call",
                                                                       "detail": "The tool call was not valid JSON."}}))
            ids = ids + renderer.enc(tool_block(results))
            seen += "\n" + "\n".join(results)
            layer.observe("\n".join(results))
            continue
        if pending:
            nxt = pending.pop(0)
            tr.users.append(nxt)
            seen += "\n" + nxt
            layer.observe(nxt)
            ids = ids + renderer.enc(user_block(nxt))
            continue
        tr.stopped = "final_answer"
        break
    else:
        tr.stopped = "max_steps"
    tr.prompt_tokens_last = len(ids)
    tr.audit = list(layer.audit.rows)
    return tr
