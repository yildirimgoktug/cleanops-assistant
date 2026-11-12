"""Backends that execute the 16 tools as a given user.

`MockBackend` is the ground truth for data generation and evaluation. It runs
the tools against a synthetic `World` and enforces the platform's permission
rules, restated here in code:

* Scoping. Every role sees only its own slice of the data. Objects outside
  that slice are answered with 404 (not 403), so the assistant cannot learn
  whether they exist. Lists silently narrow.
* Role refusals. A role that may never use a tool at all gets 403 (invoices
  for field staff, non-decision status moves by customers) or a stable 400
  code (ticket creation by field staff, a message type the role may not post,
  a status move the role may not make).
* The ticket status workflow is a fixed transition table; who may make each
  move depends on the role, and some moves need a note, a reason or an
  assigned staff member.
* Extra-work prices are decided by the customer; provider users may decide on
  the customer's behalf only with a reason (and a building manager only when
  that permission was not revoked).

Results are compact JSON dicts shaped like a REST response, or an error
object `{"error": {"status": <code>, "code": ..., "detail": ...}}`.
"""
from __future__ import annotations

import abc
import datetime as dt
from typing import Any

from .world import (SA, CA, BM, STAFF, CU, CLM, CCA, CUSTOMER_ROLES, OPEN_STATUSES, World, Ticket, Message,
                    User)

READ_TOOLS = {"search_records", "list_tickets", "get_ticket", "get_ticket_stats", "list_ticket_messages",
              "list_notifications", "list_buildings", "list_customers", "list_extra_work_requests",
              "get_extra_work_request", "list_invoices", "get_invoice"}
WRITE_TOOLS = {"create_ticket", "add_ticket_message", "change_ticket_status", "decide_extra_work"}
ALL_TOOLS = READ_TOOLS | WRITE_TOOLS

MANAGERS = {SA, CA, BM}

# (from, to) -> roles that may make the move (customer roles: see CUSTOMER_DECISIONS)
TRANSITIONS = {
    ("OPEN", "IN_PROGRESS"): MANAGERS,
    ("OPEN", "ACKNOWLEDGED"): MANAGERS,
    ("ACKNOWLEDGED", "IN_PROGRESS"): MANAGERS | {STAFF},
    ("ACKNOWLEDGED", "ON_HOLD"): MANAGERS,
    ("IN_PROGRESS", "ON_HOLD"): MANAGERS,
    ("ON_HOLD", "IN_PROGRESS"): MANAGERS,
    ("IN_PROGRESS", "WAITING_MANAGER_REVIEW"): MANAGERS | {STAFF},
    ("IN_PROGRESS", "WAITING_CUSTOMER_APPROVAL"): MANAGERS | {STAFF},
    ("WAITING_MANAGER_REVIEW", "WAITING_CUSTOMER_APPROVAL"): MANAGERS,
    ("WAITING_MANAGER_REVIEW", "IN_PROGRESS"): MANAGERS,
    ("WAITING_CUSTOMER_APPROVAL", "APPROVED"): MANAGERS,   # providers only as an override with a reason
    ("WAITING_CUSTOMER_APPROVAL", "REJECTED"): MANAGERS,   # idem
    ("REJECTED", "IN_PROGRESS"): MANAGERS,
    ("APPROVED", "CLOSED"): {SA, CA},
    ("CLOSED", "REOPENED_BY_ADMIN"): {SA, CA},
    ("REOPENED_BY_ADMIN", "IN_PROGRESS"): MANAGERS,
}
CUSTOMER_DECISIONS = {("WAITING_CUSTOMER_APPROVAL", "APPROVED"), ("WAITING_CUSTOMER_APPROVAL", "REJECTED")}
COMPLETION_TARGETS = {"WAITING_MANAGER_REVIEW", "WAITING_CUSTOMER_APPROVAL"}

MESSAGE_TYPES_BY_ROLE = {
    SA: {"PUBLIC_REPLY", "INTERNAL_NOTE", "STAFF_OPERATIONAL", "STAFF_COMPLETION"},
    CA: {"PUBLIC_REPLY", "INTERNAL_NOTE", "STAFF_OPERATIONAL", "STAFF_COMPLETION"},
    BM: {"PUBLIC_REPLY", "INTERNAL_NOTE", "STAFF_OPERATIONAL", "STAFF_COMPLETION"},
    STAFF: {"STAFF_OPERATIONAL", "STAFF_COMPLETION"},
    CU: {"PUBLIC_REPLY", "CUSTOMER_INTERNAL"},
    CLM: {"PUBLIC_REPLY", "CUSTOMER_INTERNAL"},
    CCA: {"PUBLIC_REPLY", "CUSTOMER_INTERNAL"},
}
MESSAGE_TYPES_VISIBLE = {
    SA: {"PUBLIC_REPLY", "INTERNAL_NOTE", "STAFF_OPERATIONAL", "STAFF_COMPLETION", "CUSTOMER_INTERNAL"},
    CA: {"PUBLIC_REPLY", "INTERNAL_NOTE", "STAFF_OPERATIONAL", "STAFF_COMPLETION"},
    BM: {"PUBLIC_REPLY", "INTERNAL_NOTE", "STAFF_OPERATIONAL", "STAFF_COMPLETION"},
    STAFF: {"STAFF_OPERATIONAL", "STAFF_COMPLETION"},
    CU: {"PUBLIC_REPLY", "STAFF_COMPLETION", "CUSTOMER_INTERNAL"},
    CLM: {"PUBLIC_REPLY", "STAFF_COMPLETION", "CUSTOMER_INTERNAL"},
    CCA: {"PUBLIC_REPLY", "STAFF_COMPLETION", "CUSTOMER_INTERNAL"},
}
DEFAULT_MESSAGE_TYPE = {STAFF: "STAFF_OPERATIONAL"}  # everyone else: PUBLIC_REPLY

PAGE_SIZE = 25


def err(status: int, code: str, detail: str) -> dict:
    return {"error": {"status": status, "code": code, "detail": detail}}


def is_error(res: Any) -> bool:
    return isinstance(res, dict) and "error" in res


# ---------------------------------------------------------------------------
# Scope rules
# ---------------------------------------------------------------------------
def customer_building_ids(world: World, u: User) -> set:
    """Buildings a customer user may act on: all of the customer's buildings for a company admin,
    otherwise the buildings of the user's own access rows."""
    if u.role == CCA:
        c = world.customer(u.customer_id)
        return set(c.building_ids) if c else set()
    return set(u.access_building_ids)


def can_see_ticket(world: World, u: User, t) -> bool:
    """Shared rule for tickets and extra-work requests (`t` has company/building/customer/created_by)."""
    if u.role == SA:
        return True
    if u.role == CA:
        return t.company_id == u.company_id
    if u.role == BM:
        return t.building_id in u.building_ids
    if u.role == STAFF:
        if isinstance(t, Ticket) and u.id in t.assigned_staff_ids:
            return True
        return u.staff_visibility.get(t.building_id) == "BUILDING_READ" and isinstance(t, Ticket)
    if u.role in CUSTOMER_ROLES:
        if t.customer_id != u.customer_id:
            return False
        if u.role == CCA:
            return True
        if t.building_id not in u.access_building_ids:
            return False
        return u.role == CLM or t.created_by == u.id
    return False


def visible_tickets(world: World, u: User, include_archived: bool = True):
    return [t for t in world.tickets if can_see_ticket(world, u, t) and (include_archived or not t.archived)]


def can_see_ew(world: World, u: User, e) -> bool:
    if u.role == STAFF:
        return False  # field staff have no access to extra work at all
    return can_see_ticket(world, u, e)


def can_see_building(world: World, u: User, b) -> bool:
    if u.role == SA:
        return True
    if not b.is_active:
        return False
    if u.role == CA:
        return b.company_id == u.company_id
    if u.role == BM:
        return b.id in u.building_ids
    if u.role == STAFF:
        return b.id in u.staff_visibility  # any visibility level lists the building
    return b.id in customer_building_ids(world, u)


def can_see_customer(world: World, u: User, c) -> bool:
    if u.role == SA:
        return True
    if u.role == CA:
        return c.company_id == u.company_id
    if u.role == BM:
        return bool(set(c.building_ids) & set(u.building_ids))
    if u.role == STAFF:
        return False
    return c.id == u.customer_id


def can_see_invoice(world: World, u: User, inv) -> bool:
    if u.role == SA:
        return True
    if u.role == CA:
        return inv.company_id == u.company_id
    if u.role == BM:
        # company-wide: every invoice of a company where the manager manages any building
        return any(world.building(b).company_id == inv.company_id for b in u.building_ids)
    if u.role in CUSTOMER_ROLES:
        return inv.customer_id == u.customer_id and inv.status == "SENT"
    return False


def allowed_next_statuses(world: World, u: User, t: Ticket) -> list:
    """Statuses this user may move the ticket to by the workflow table (requirements such as
    notes or reasons are checked when the move is made)."""
    out = []
    for (frm, to), roles in TRANSITIONS.items():
        if frm != t.status:
            continue
        if u.role in CUSTOMER_ROLES:
            if (frm, to) in CUSTOMER_DECISIONS and customer_may_decide(world, u, t):
                out.append(to)
            continue
        if u.role not in roles:
            continue
        if u.role == STAFF and u.id not in t.assigned_staff_ids:
            continue
        if u.role == STAFF and to in COMPLETION_TARGETS and to != world.building(t.building_id).staff_completion_route:
            continue
        if u.role == BM and (frm, to) in CUSTOMER_DECISIONS and not u.bm_may_override:
            continue
        out.append(to)
    return out


def customer_may_decide(world: World, u: User, obj) -> bool:
    if u.role not in CUSTOMER_ROLES or obj.customer_id != u.customer_id:
        return False
    if u.role == CCA:
        return True
    if obj.building_id not in u.access_building_ids:
        return False
    return u.role == CLM or obj.created_by == u.id


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------
class Backend(abc.ABC):
    """Executes one tool call as one user. Implementations: MockBackend (here), LiveBackend (later)."""

    @abc.abstractmethod
    def call(self, user_id: int, tool: str, args: dict) -> dict:
        """Run `tool` with `args` as the user and return the JSON result or an error object."""

    @abc.abstractmethod
    def user_context(self, user_id: int) -> dict:
        """What the tool layer knows about the signed-in user (name, role, scope summary)."""


class LiveBackend(Backend):
    """Placeholder for an HTTP backend against a real development instance.

    It will hold the signed-in user's access token, map each tool to the
    platform's REST endpoint, translate arguments into query/body parameters,
    trim the responses to the same compact shapes MockBackend returns, and map
    HTTP errors onto the same `{"error": {...}}` object. Not implemented in
    this version: the real platform could not be run on the development
    machine. The endpoint mapping is kept outside this repository.
    """

    def call(self, user_id, tool, args):  # pragma: no cover
        raise NotImplementedError("LiveBackend is not implemented yet")

    def user_context(self, user_id):  # pragma: no cover
        raise NotImplementedError


class MockBackend(Backend):
    def __init__(self, world: World):
        self.w = world
        self.log = []  # (user_id, tool, args, ok)

    # ------------------------------------------------------------------
    def call(self, user_id: int, tool: str, args: dict) -> dict:
        u = self.w.user(user_id)
        if u is None:
            return err(401, "not_authenticated", "Unknown user.")
        if tool not in ALL_TOOLS:
            return err(404, "unknown_tool", f"Unknown tool {tool}.")
        res = getattr(self, "_" + tool)(u, dict(args or {}))
        self.log.append((user_id, tool, args, not is_error(res)))
        return res

    def user_context(self, user_id: int) -> dict:
        u = self.w.user(user_id)
        ctx = {"user_id": u.id, "name": u.full_name, "role": u.role, "language": u.language}
        if u.company_id:
            ctx["company"] = {"id": u.company_id, "name": self.w.company(u.company_id).name}
        if u.role == BM:
            ctx["buildings"] = [self._bref(b) for b in u.building_ids]
        elif u.role == STAFF:
            ctx["buildings"] = [self._bref(b) for b in sorted(u.staff_visibility)]
        elif u.role in CUSTOMER_ROLES:
            c = self.w.customer(u.customer_id)
            ctx["customer"] = {"id": c.id, "name": c.name}
            ctx["buildings"] = [self._bref(b) for b in sorted(customer_building_ids(self.w, u))]
        return ctx

    # helpers -----------------------------------------------------------
    def _bref(self, bid):
        b = self.w.building(bid)
        return {"id": b.id, "name": b.name} if b else None

    def _cname(self, cid):
        c = self.w.customer(cid)
        return c.name if c else None

    def _ticket_row(self, t):
        return {"id": t.id, "ticket_no": t.ticket_no, "title": t.title, "status": t.status, "priority": t.priority,
                "building": self.w.building(t.building_id).name, "customer": self._cname(t.customer_id),
                "created_at": t.created_at}

    def _ticket_detail(self, u, t):
        d = {"id": t.id, "ticket_no": t.ticket_no, "title": t.title, "description": t.description,
             "status": t.status, "priority": t.priority, "type": t.type, "room": t.room_label,
             "building": self._bref(t.building_id), "customer": {"id": t.customer_id, "name": self._cname(t.customer_id)},
             "created_at": t.created_at, "created_by": self.w.user(t.created_by).full_name,
             "assigned_staff": [self.w.user(s).full_name for s in t.assigned_staff_ids],
             "scheduled_date": t.scheduled_date,
             "allowed_next_statuses": allowed_next_statuses(self.w, u, t)}
        return d

    def _ew_row(self, e):
        return {"id": e.id, "title": e.title, "status": e.status, "building": self.w.building(e.building_id).name,
                "customer": self._cname(e.customer_id), "total_amount": e.total_amount, "deadline": e.deadline}

    def _inv_row(self, u, i):
        r = {"id": i.id, "number": i.number, "status": i.status, "customer": self._cname(i.customer_id),
             "period": f"{i.period_year}-{i.period_month:02d}", "total_amount": round(i.subtotal * 1.21, 2)}
        if u.role in CUSTOMER_ROLES:
            r.pop("status")
        return r

    @staticmethod
    def _page(rows, args):
        page = int(args.get("page") or 1)
        size = int(args.get("page_size") or PAGE_SIZE)
        start = (page - 1) * size
        return {"count": len(rows), "results": rows[start:start + size]}

    # ------------------------------------------------------------------
    # Read tools
    # ------------------------------------------------------------------
    def _search_records(self, u, a):
        q = (a.get("q") or "").strip()
        if len(q) < 2:
            return err(400, "query_too_short", "Search text must be at least 2 characters.")
        ql = q.lower()
        w = self.w
        tickets = [t for t in w.tickets if can_see_ticket(w, u, t) and (ql in t.ticket_no.lower() or ql in t.title.lower())]
        ews = [e for e in w.extra_work if can_see_ew(w, u, e) and (ql in e.title.lower() or q == str(e.id))]
        custs = [c for c in w.customers if can_see_customer(w, u, c) and ql in c.name.lower()]
        blds = [b for b in w.buildings if can_see_building(w, u, b) and (ql in b.name.lower() or ql in b.city.lower())]
        people = []
        if u.role in (SA, CA):
            people = [p for p in w.users if ql in p.full_name.lower() and
                      (u.role == SA or p.company_id == u.company_id or
                       (p.customer_id and w.customer(p.customer_id).company_id == u.company_id))]
        lim = 5
        return {"q": q, "groups": {
            "tickets": [{"id": t.id, "ticket_no": t.ticket_no, "title": t.title, "status": t.status,
                         "building": w.building(t.building_id).name} for t in tickets[-lim:][::-1]],
            "extra_work": [{"id": e.id, "title": e.title, "status": e.status} for e in ews[-lim:][::-1]],
            "customers": [{"id": c.id, "name": c.name} for c in custs[:lim]],
            "buildings": [{"id": b.id, "name": b.name, "city": b.city} for b in blds[:lim]],
            "people": [{"id": p.id, "full_name": p.full_name, "role": p.role} for p in people[:lim]],
        }, "truncated": any(len(x) > lim for x in (tickets, ews, custs, blds, people))}

    def _filter_tickets(self, u, a):
        w = self.w
        today = dt.date.fromisoformat(w.today)
        rows = [t for t in w.tickets if can_see_ticket(w, u, t)]
        rows = [t for t in rows if t.archived == bool(a.get("archived", False))]
        if a.get("status"):
            rows = [t for t in rows if t.status in a["status"]]
        if a.get("priority"):
            rows = [t for t in rows if t.priority in a["priority"]]
        if a.get("type"):
            rows = [t for t in rows if t.type in a["type"]]
        if a.get("building_id"):
            rows = [t for t in rows if t.building_id == a["building_id"]]
        if a.get("customer_id"):
            rows = [t for t in rows if t.customer_id == a["customer_id"]]
        if a.get("my_jobs"):
            rows = [t for t in rows if u.id in t.assigned_staff_ids]
        if a.get("my_managed"):
            rows = [t for t in rows if t.manager_id == u.id]
        if a.get("search"):
            s = a["search"].lower()
            rows = [t for t in rows if s in t.ticket_no.lower() or s in t.title.lower() or s in t.room_label.lower()
                    or (u.role not in CUSTOMER_ROLES and s in t.description.lower())]
        if a.get("date_from"):
            rows = [t for t in rows if t.created_at >= a["date_from"]]
        if a.get("date_to"):
            rows = [t for t in rows if t.created_at <= a["date_to"]]
        ag = a.get("agenda")
        finished = {"APPROVED", "CLOSED", "REJECTED", "CONVERTED_TO_EXTRA_WORK", "WAITING_CUSTOMER_APPROVAL",
                    "WAITING_MANAGER_REVIEW"}
        if ag == "today":
            rows = [t for t in rows if t.scheduled_date == w.today]
        elif ag == "upcoming":
            rows = [t for t in rows if t.scheduled_date and t.scheduled_date > w.today]
        elif ag == "overdue":
            rows = [t for t in rows if t.scheduled_date and t.scheduled_date < w.today and t.status not in finished]
        elif ag == "unscheduled":
            rows = [t for t in rows if not t.scheduled_date and t.status not in finished]
        if a.get("awaiting_customer_approval_days") is not None:
            n = a["awaiting_customer_approval_days"]
            rows = [t for t in rows if t.status == "WAITING_CUSTOMER_APPROVAL" and
                    (today - dt.date.fromisoformat(t.updated_at)).days >= n]
        return rows

    def _list_tickets(self, u, a):
        rows = self._filter_tickets(u, a)
        order = a.get("ordering") or "-created_at"
        key = order.lstrip("-")
        rows.sort(key=lambda t: (getattr(t, key), t.id), reverse=order.startswith("-"))
        return self._page([self._ticket_row(t) for t in rows], a)

    def _get_ticket(self, u, a):
        t = self.w.ticket(a.get("ticket_id"))
        if t is None or not can_see_ticket(self.w, u, t):
            return err(404, "not_found", "Ticket not found.")
        return self._ticket_detail(u, t)

    def _get_ticket_stats(self, u, a):
        rows = self._filter_tickets(u, {k: a[k] for k in ("date_from", "date_to", "customer_id", "archived") if k in a})
        by_status, by_prio = {}, {}
        for t in rows:
            by_status[t.status] = by_status.get(t.status, 0) + 1
            by_prio[t.priority] = by_prio.get(t.priority, 0) + 1
        return {"total": len(rows), "by_status": dict(sorted(by_status.items())), "by_priority": dict(sorted(by_prio.items())),
                "open": sum(1 for t in rows if t.status in OPEN_STATUSES),
                "waiting_customer_approval": by_status.get("WAITING_CUSTOMER_APPROVAL", 0),
                "urgent": sum(1 for t in rows if t.priority == "URGENT" and t.status in OPEN_STATUSES)}

    def _list_ticket_messages(self, u, a):
        t = self.w.ticket(a.get("ticket_id"))
        if t is None or not can_see_ticket(self.w, u, t):
            return err(404, "not_found", "Ticket not found.")
        vis = MESSAGE_TYPES_VISIBLE[u.role]
        rows = [{"id": m.id, "author": self.w.user(m.author_id).full_name, "type": m.message_type,
                 "message": m.message, "created_at": m.created_at}
                for m in self.w.messages if m.ticket_id == t.id and m.message_type in vis]
        return self._page(rows, a)

    def _list_notifications(self, u, a):
        rows = sorted([n for n in self.w.notifications if n.recipient_id == u.id], key=lambda n: (n.created_at, n.id),
                      reverse=True)
        res = self._page([{"id": n.id, "title": n.title, "is_read": n.is_read, "created_at": n.created_at} for n in rows], a)
        res["unread_count"] = sum(1 for n in rows if not n.is_read)
        return res

    def _list_buildings(self, u, a):
        rows = [b for b in self.w.buildings if can_see_building(self.w, u, b)]
        if a.get("search"):
            s = a["search"].lower()
            rows = [b for b in rows if s in b.name.lower() or s in b.city.lower() or s in b.address.lower()
                    or s in b.postal_code.lower()]
        if a.get("city"):
            rows = [b for b in rows if b.city.lower() == a["city"].lower()]
        order = a.get("ordering") or "name"
        key = {"name": "name", "city": "city", "created_at": "id"}[order.lstrip("-")]
        rows.sort(key=lambda b: getattr(b, key), reverse=order.startswith("-"))
        return self._page([{"id": b.id, "name": b.name, "city": b.city, "address": b.address,
                            "customers": [c.name for c in self.w.customers if b.id in c.building_ids
                                          and can_see_customer(self.w, u, c)]} for b in rows], a)

    def _list_customers(self, u, a):
        rows = [c for c in self.w.customers if can_see_customer(self.w, u, c)]
        if a.get("search"):
            s = a["search"].lower()
            rows = [c for c in rows if s in c.name.lower() or s in c.contact_email.lower()]
        if a.get("lifecycle"):
            rows = [c for c in rows if c.lifecycle == a["lifecycle"]]
        order = a.get("ordering") or "name"
        key = "name" if order.lstrip("-") == "name" else "id"
        rows.sort(key=lambda c: getattr(c, key), reverse=order.startswith("-"))
        return self._page([{"id": c.id, "name": c.name, "linked_building_ids": c.building_ids,
                            "lifecycle": c.lifecycle} for c in rows], a)

    def _list_extra_work_requests(self, u, a):
        rows = [e for e in self.w.extra_work if can_see_ew(self.w, u, e)]
        if a.get("status"):
            rows = [e for e in rows if e.status in a["status"]]
        if a.get("customer_id"):
            rows = [e for e in rows if e.customer_id == a["customer_id"]]
        if a.get("building_id"):
            rows = [e for e in rows if e.building_id == a["building_id"]]
        if a.get("routing_decision"):
            rows = [e for e in rows if e.routing_decision == a["routing_decision"]]
        if a.get("request_intent"):
            rows = [e for e in rows if e.request_intent in a["request_intent"]]
        if a.get("overdue"):
            rows = [e for e in rows if e.deadline and e.deadline < self.w.today and e.status not in
                    ("COMPLETED", "CANCELLED", "CUSTOMER_REJECTED")]
        if a.get("deadline_before"):
            rows = [e for e in rows if e.deadline and e.deadline <= a["deadline_before"]]
        if a.get("deadline_after"):
            rows = [e for e in rows if e.deadline and e.deadline >= a["deadline_after"]]
        rows.sort(key=lambda e: (e.requested_at, e.id), reverse=True)
        return self._page([self._ew_row(e) for e in rows], a)

    def _ew_actions(self, u, e):
        waiting = e.status == "PRICING_PROPOSED"
        if u.role in CUSTOMER_ROLES:
            ok = waiting and customer_may_decide(self.w, u, e)
        elif u.role == BM:
            ok = waiting and u.bm_may_override
        else:
            ok = waiting and u.role in (SA, CA)
        return {"can_approve": ok, "can_reject": ok, "decision_needs_reason": u.role not in CUSTOMER_ROLES}

    def _get_extra_work_request(self, u, a):
        e = self.w.ew(a.get("extra_work_id"))
        if e is None or not can_see_ew(self.w, u, e):
            return err(404, "not_found", "Extra-work request not found.")
        d = self._ew_row(e)
        d.update({"description": e.description, "building": self._bref(e.building_id),
                  "customer": {"id": e.customer_id, "name": self._cname(e.customer_id)},
                  "lines": e.lines, "quote_sent": e.has_sent_quote, "requested_at": e.requested_at,
                  "created_by": self.w.user(e.created_by).full_name})
        d.update(self._ew_actions(u, e))
        return d

    def _list_invoices(self, u, a):
        if u.role == STAFF:
            return err(403, "invoices_not_available", "Invoices are not available for field staff.")
        rows = [i for i in self.w.invoices if can_see_invoice(self.w, u, i)]
        if u.role not in CUSTOMER_ROLES:  # provider-only filters; customers get them ignored
            if a.get("status"):
                rows = [i for i in rows if i.status == a["status"]]
            if a.get("customer_id"):
                rows = [i for i in rows if i.customer_id == a["customer_id"]]
            if a.get("building_id"):
                rows = [i for i in rows if i.building_id == a["building_id"]]
        if a.get("period_year"):
            rows = [i for i in rows if i.period_year == a["period_year"]]
        if a.get("period_month"):
            rows = [i for i in rows if i.period_month == a["period_month"]]
        rows.sort(key=lambda i: (i.period_year, i.period_month, i.id), reverse=True)
        out = [self._inv_row(u, i) for i in rows]
        if u.role in CUSTOMER_ROLES:
            return {"count": len(out), "results": out}
        return self._page(out, a)

    def _get_invoice(self, u, a):
        if u.role == STAFF:
            return err(403, "invoices_not_available", "Invoices are not available for field staff.")
        i = self.w.invoice(a.get("invoice_id"))
        if i is None or not can_see_invoice(self.w, u, i):
            return err(404, "not_found", "Invoice not found.")
        d = self._inv_row(u, i)
        d.update({"lines": i.lines, "subtotal": i.subtotal, "vat": round(i.subtotal * 0.21, 2),
                  "building": self.w.building(i.building_id).name if i.building_id else None})
        return d

    # ------------------------------------------------------------------
    # Write tools
    # ------------------------------------------------------------------
    def _next_id(self, coll):
        return max([x.id for x in coll] + [0]) + 1

    def _create_ticket(self, u, a):
        w = self.w
        if u.role == STAFF:
            return err(400, "create_not_allowed", "You do not have permission to create tickets.")
        b = w.building(a.get("building_id"))
        c = w.customer(a.get("customer_id"))
        if b is None or not b.is_active:
            return err(400, "invalid_building", "Unknown or inactive building.")
        if c is None:
            return err(400, "invalid_customer", "Unknown customer.")
        if u.role == CA and b.company_id != u.company_id:
            return err(400, "building_not_allowed", "You cannot create tickets for this building.")
        if u.role == BM and b.id not in u.building_ids:
            return err(400, "building_not_allowed", "You cannot create tickets for this building.")
        if u.role in CUSTOMER_ROLES:
            if c.id != u.customer_id:
                return err(400, "customer_not_allowed", "You cannot create tickets for this customer.")
            if b.id not in customer_building_ids(w, u):
                return err(400, "building_not_allowed", "You cannot create tickets for this building.")
        if b.id not in c.building_ids:
            return err(400, "customer_not_linked", "This customer is not linked to this building.")
        title = (a.get("title") or "").strip()
        desc = (a.get("description") or "").strip()
        if not title or not desc:
            return err(400, "missing_field", "Title and description are required.")
        tid = self._next_id(w.tickets)
        seq = max(int(t.ticket_no.split("-")[-1]) for t in w.tickets) + 1
        bms = [x for x in w.users if x.role == BM and b.id in x.building_ids]
        t = Ticket(tid, f"TCK-{w.today[:4]}-{seq:06d}", b.company_id, b.id, c.id, title, desc,
                   a.get("room_label") or "", "REPORT" if u.role in CUSTOMER_ROLES else (a.get("type") or "REPORT"),
                   a.get("priority") or "NORMAL", "OPEN", u.id, w.today, w.today, [], bms[0].id if bms else None,
                   None, False, a.get("customer_wanted_date"))
        t.history = [{"to": "OPEN", "on": w.today}]
        w.tickets.append(t)
        return {"id": t.id, "ticket_no": t.ticket_no, "title": t.title, "status": t.status, "priority": t.priority,
                "building": b.name, "customer": c.name}

    def _add_ticket_message(self, u, a):
        w = self.w
        t = w.ticket(a.get("ticket_id"))
        if t is None or not can_see_ticket(w, u, t):
            return err(404, "not_found", "Ticket not found.")
        mt = a.get("message_type") or DEFAULT_MESSAGE_TYPE.get(u.role, "PUBLIC_REPLY")
        if mt not in MESSAGE_TYPES_BY_ROLE[u.role]:
            return err(400, "message_type_not_allowed", f"You may not post a {mt} message.")
        text = (a.get("message") or "").strip()
        if not text:
            return err(400, "missing_field", "Message text is required.")
        m = Message(self._next_id(w.messages), t.id, u.id, mt, text, w.today)
        w.messages.append(m)
        return {"id": m.id, "ticket_id": t.id, "message_type": mt, "created_at": m.created_at}

    def _change_ticket_status(self, u, a):
        w = self.w
        t = w.ticket(a.get("ticket_id"))
        if t is None or not can_see_ticket(w, u, t):
            return err(404, "not_found", "Ticket not found.")
        to = a.get("to_status")
        frm = t.status
        note = (a.get("note") or "").strip()
        reason = (a.get("override_reason") or "").strip()
        if to == frm:
            return err(400, "no_op_transition", f"The ticket is already {frm}.")
        pair = (frm, to)
        if u.role in CUSTOMER_ROLES:
            if to not in ("APPROVED", "REJECTED"):
                return err(403, "customer_status_not_allowed", "Customer users can only approve or reject finished work.")
            if pair not in CUSTOMER_DECISIONS or not customer_may_decide(w, u, t):
                return err(400, "forbidden_transition", f"You cannot move this ticket from {frm} to {to}.")
            if to == "REJECTED" and not note:
                return err(400, "rejection_note_required", "Please say why you reject the work (note).")
            return self._apply(u, t, to, note)
        if pair not in TRANSITIONS:
            if u.role == SA and to != "CONVERTED_TO_EXTRA_WORK" and frm != "CONVERTED_TO_EXTRA_WORK":
                if not reason:
                    return err(400, "override_reason_required", "A move outside the workflow needs an override_reason.")
                return self._apply(u, t, to, note or reason)
            return err(400, "forbidden_transition", f"You cannot move this ticket from {frm} to {to}.")
        if u.role not in TRANSITIONS[pair]:
            return err(400, "forbidden_transition", f"Your role cannot move this ticket from {frm} to {to}.")
        if u.role == STAFF:
            if u.id not in t.assigned_staff_ids:
                return err(400, "forbidden_transition", "Only the assigned staff member can do this.")
            if to in COMPLETION_TARGETS and to != w.building(t.building_id).staff_completion_route:
                return err(400, "staff_completion_route_mismatch",
                           f"Finished work at this building goes to {w.building(t.building_id).staff_completion_route}.")
        if pair in CUSTOMER_DECISIONS:  # provider deciding on the customer's behalf
            if u.role == BM and not u.bm_may_override:
                return err(400, "bm_override_disabled", "You may not decide on the customer's behalf.")
            if not reason:
                return err(400, "override_reason_required", "Deciding for the customer needs an override_reason.")
        if to in COMPLETION_TARGETS and frm == "IN_PROGRESS" and not note:
            return err(400, "completion_note_required", "Reporting work as done needs a note describing what was done.")
        if pair == ("WAITING_MANAGER_REVIEW", "IN_PROGRESS") and not note:
            return err(400, "note_required", "Sending work back needs a note.")
        if to == "IN_PROGRESS" and frm in ("OPEN", "ACKNOWLEDGED") and not t.assigned_staff_ids:
            return err(400, "transition_requirements_unmet", "Assign a staff member before starting the work.")
        return self._apply(u, t, to, note or reason)

    def _apply(self, u, t, to, note):
        t.history.append({"to": to, "on": self.w.today, "by": u.id})
        t.status = to
        t.updated_at = self.w.today
        if note:
            self.w.messages.append(Message(self._next_id(self.w.messages), t.id, u.id,
                                           "STAFF_COMPLETION" if u.role == STAFF else
                                           ("CUSTOMER_INTERNAL" if u.role in CUSTOMER_ROLES else "INTERNAL_NOTE"),
                                           note, self.w.today))
        return {"id": t.id, "ticket_no": t.ticket_no, "status": t.status,
                "allowed_next_statuses": allowed_next_statuses(self.w, u, t)}

    def _decide_extra_work(self, u, a):
        w = self.w
        e = w.ew(a.get("extra_work_id"))
        if e is None or not can_see_ew(w, u, e):
            return err(404, "not_found", "Extra-work request not found.")
        decision = a.get("decision")
        reason = (a.get("reason") or "").strip()
        if decision not in ("approve", "reject"):
            return err(400, "invalid_decision", "decision must be approve or reject.")
        if e.status != "PRICING_PROPOSED":
            return err(400, "invalid_transition", f"This request is {e.status}; there is no price waiting for a decision.")
        if u.role in CUSTOMER_ROLES:
            if not customer_may_decide(w, u, e):
                return err(400, "forbidden_transition", "You cannot decide on this request.")
            if decision == "reject" and not reason:
                return err(400, "rejection_note_required", "Please give a reason for the rejection.")
        else:
            if u.role == BM and not u.bm_may_override:
                return err(400, "bm_override_disabled", "You may not decide on the customer's behalf.")
            if not reason:
                return err(400, "override_reason_required", "Deciding for the customer needs a reason.")
        e.status = "CUSTOMER_APPROVED" if decision == "approve" else "CUSTOMER_REJECTED"
        e.decision_reason = reason or None
        return {"id": e.id, "title": e.title, "status": e.status, "total_amount": e.total_amount}
