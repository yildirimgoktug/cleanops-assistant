"""Rule tests for MockBackend. The mock is the ground truth for training data and evaluation,
so every permission rule it implements is pinned here."""
import copy

import pytest

from assistant.world import (make_world, SA, CA, BM, STAFF, CU, CLM, CCA, TRAIN_SEEDS, TEST_SEEDS, POOLS,
                             TICKET_STATUSES)
from assistant.backend import (MockBackend, visible_tickets, can_see_ticket, allowed_next_statuses, TRANSITIONS,
                               is_error, WRITE_TOOLS, READ_TOOLS)


@pytest.fixture(params=[("train", 1), ("train", 2), ("test", 1)])
def world(request):
    fam, seed = request.param
    return make_world(seed, fam)


def first(seq, msg="no candidate in world"):
    seq = list(seq)
    if not seq:
        pytest.skip(msg)
    return seq[0]


def users(w, role):
    return w.users_with_role(role)


def code(res):
    return res["error"]["status"], res["error"]["code"]


# ---------------------------------------------------------------- world ----
def test_world_is_deterministic():
    a, b = make_world(3, "train"), make_world(3, "train")
    assert a.to_dict() == b.to_dict()
    assert make_world(4, "train").to_dict() != a.to_dict()


def test_world_has_all_roles_and_statuses():
    w = make_world(1, "train")
    assert {u.role for u in w.users} == {SA, CA, BM, STAFF, CU, CLM, CCA}
    statuses = set()
    for s in TRAIN_SEEDS[:4]:
        statuses |= {t.status for t in make_world(s, "train").tickets}
    assert statuses == set(TICKET_STATUSES)
    assert len(w.companies) == 2
    assert {i.status for i in w.invoices} == {"DRAFT", "ISSUED", "SENT"} or {i.status for i in w.invoices} >= {"DRAFT", "SENT"}
    assert any(e.status == "PRICING_PROPOSED" and e.has_sent_quote for e in w.extra_work)


def test_train_and_test_worlds_are_disjoint():
    train_ids, train_names = set(), set()
    for s in TRAIN_SEEDS:
        w = make_world(s, "train")
        train_ids |= w.all_ids()
        train_names |= {x.name for x in w.buildings + w.customers + w.companies} | {u.full_name for u in w.users}
        train_names |= {t.ticket_no for t in w.tickets}
    for s in TEST_SEEDS:
        w = make_world(s, "test")
        assert not (w.all_ids() & train_ids)
        names = {x.name for x in w.buildings + w.customers + w.companies} | {u.full_name for u in w.users}
        names |= {t.ticket_no for t in w.tickets}
        assert not (names & train_names)
    assert not set(POOLS["train"]["customers"]) & set(POOLS["test"]["customers"])
    assert not {t[0] for t in POOLS["train"]["tickets"]} & {t[0] for t in POOLS["test"]["tickets"]}


# -------------------------------------------------------------- scoping ----
def test_super_admin_sees_everything(world):
    sa = users(world, SA)[0]
    assert len(visible_tickets(world, sa)) == len(world.tickets)
    b = MockBackend(world)
    res = b.call(sa.id, "list_buildings", {"page_size": 200})
    assert res["count"] == len(world.buildings)  # including inactive buildings


def test_company_admin_scoped_to_company(world):
    b = MockBackend(world)
    for ca in users(world, CA):
        vis = visible_tickets(world, ca)
        assert vis and all(t.company_id == ca.company_id for t in vis)
        other = first(t for t in world.tickets if t.company_id != ca.company_id)
        assert code(b.call(ca.id, "get_ticket", {"ticket_id": other.id})) == (404, "not_found")
        res = b.call(ca.id, "list_buildings", {"page_size": 200})
        assert all(world.building(r["id"]).company_id == ca.company_id and world.building(r["id"]).is_active
                   for r in res["results"])


def test_building_manager_scoped_to_buildings(world):
    b = MockBackend(world)
    for bm in users(world, BM):
        vis = visible_tickets(world, bm)
        assert all(t.building_id in bm.building_ids for t in vis)
        res = b.call(bm.id, "list_tickets", {"page_size": 200})
        assert {r["id"] for r in res["results"]} == {t.id for t in vis if not t.archived}
        out = first(t for t in world.tickets if t.company_id == bm.company_id and t.building_id not in bm.building_ids)
        assert code(b.call(bm.id, "get_ticket", {"ticket_id": out.id}))[0] == 404


def test_staff_scope_assigned_or_building_read(world):
    for st in users(world, STAFF):
        for t in world.tickets:
            expected = st.id in t.assigned_staff_ids or st.staff_visibility.get(t.building_id) == "BUILDING_READ"
            assert can_see_ticket(world, st, t) == expected


def test_staff_assigned_only_lists_building_but_not_its_tickets():
    for s in TRAIN_SEEDS:
        w = make_world(s, "train")
        st = next((u for u in users(w, STAFF) if "ASSIGNED_ONLY" in u.staff_visibility.values()), None)
        if not st:
            continue
        bid = next(b for b, lvl in st.staff_visibility.items() if lvl == "ASSIGNED_ONLY")
        b = MockBackend(w)
        assert bid in {r["id"] for r in b.call(st.id, "list_buildings", {"page_size": 200})["results"]}
        unassigned = [t for t in w.tickets if t.building_id == bid and st.id not in t.assigned_staff_ids]
        assert all(not can_see_ticket(w, st, t) for t in unassigned)
        return
    pytest.skip("no ASSIGNED_ONLY staff")


def test_customer_user_sees_only_own_tickets(world):
    b = MockBackend(world)
    for cu in users(world, CU):
        vis = visible_tickets(world, cu)
        assert vis and all(t.created_by == cu.id for t in vis)
        colleague = [t for t in world.tickets if t.customer_id == cu.customer_id and t.created_by != cu.id]
        for t in colleague[:3]:
            assert code(b.call(cu.id, "get_ticket", {"ticket_id": t.id}))[0] == 404


def test_location_manager_sees_location_tickets(world):
    for clm in users(world, CLM):
        for t in world.tickets:
            exp = t.customer_id == clm.customer_id and t.building_id in clm.access_building_ids
            assert can_see_ticket(world, clm, t) == exp


def test_customer_company_admin_sees_whole_customer(world):
    for cca in users(world, CCA):
        assert {t.id for t in visible_tickets(world, cca)} == {t.id for t in world.tickets if t.customer_id == cca.customer_id}


def test_customer_cannot_see_other_customer(world):
    b = MockBackend(world)
    cca = users(world, CCA)[0]
    other = first(t for t in world.tickets if t.customer_id != cca.customer_id)
    assert code(b.call(cca.id, "get_ticket", {"ticket_id": other.id})) == (404, "not_found")
    assert code(b.call(cca.id, "list_ticket_messages", {"ticket_id": other.id}))[0] == 404
    res = b.call(cca.id, "list_customers", {})
    assert [r["id"] for r in res["results"]] == [cca.customer_id]


def test_search_respects_scope(world):
    b = MockBackend(world)
    cu = users(world, CU)[0]
    hidden = first(t for t in world.tickets if t.customer_id != cu.customer_id)
    res = b.call(cu.id, "search_records", {"q": hidden.ticket_no})
    assert res["groups"]["tickets"] == []
    assert b.call(cu.id, "search_records", {"q": "a"})["error"]["code"] == "query_too_short"
    sa = users(world, SA)[0]
    assert b.call(sa.id, "search_records", {"q": hidden.ticket_no})["groups"]["tickets"][0]["id"] == hidden.id
    # people are searchable for super admin / company admin only
    person = users(world, BM)[0]
    assert b.call(sa.id, "search_records", {"q": person.full_name})["groups"]["people"]
    assert b.call(cu.id, "search_records", {"q": person.full_name})["groups"]["people"] == []


def test_message_visibility_by_role(world):
    b = MockBackend(world)
    sa = users(world, SA)[0]
    t = first(t for t in world.tickets if {m.message_type for m in world.messages if m.ticket_id == t.id} >= {"STAFF_OPERATIONAL"})
    all_types = {r["type"] for r in b.call(sa.id, "list_ticket_messages", {"ticket_id": t.id})["results"]}
    assert "STAFF_OPERATIONAL" in all_types
    cust = first(u for u in users(world, CCA) if u.customer_id == t.customer_id)
    ctypes = {r["type"] for r in b.call(cust.id, "list_ticket_messages", {"ticket_id": t.id})["results"]}
    assert not ctypes & {"STAFF_OPERATIONAL", "INTERNAL_NOTE"}
    ca = first(u for u in users(world, CA) if u.company_id == t.company_id)
    assert "CUSTOMER_INTERNAL" not in {r["type"] for r in b.call(ca.id, "list_ticket_messages", {"ticket_id": t.id})["results"]}


def test_extra_work_scope(world):
    b = MockBackend(world)
    st = users(world, STAFF)[0]
    assert b.call(st.id, "list_extra_work_requests", {})["count"] == 0
    e = world.extra_work[0]
    assert code(b.call(st.id, "get_extra_work_request", {"extra_work_id": e.id}))[0] == 404
    for cu in users(world, CU):
        res = b.call(cu.id, "list_extra_work_requests", {"page_size": 200})
        assert all(world.ew(r["id"]).created_by == cu.id for r in res["results"])


def test_invoice_visibility(world):
    b = MockBackend(world)
    st = users(world, STAFF)[0]
    assert code(b.call(st.id, "list_invoices", {})) == (403, "invoices_not_available")
    assert code(b.call(st.id, "get_invoice", {"invoice_id": world.invoices[0].id}))[0] == 403
    for cu in users(world, CU) + users(world, CCA):
        res = b.call(cu.id, "list_invoices", {"status": "DRAFT"})  # provider-only filter is ignored
        ids = {r["id"] for r in res["results"]}
        assert ids == {i.id for i in world.invoices if i.customer_id == cu.customer_id and i.status == "SENT"}
        draft = first(i for i in world.invoices if i.customer_id == cu.customer_id and i.status == "DRAFT")
        assert code(b.call(cu.id, "get_invoice", {"invoice_id": draft.id}))[0] == 404
    for bm in users(world, BM):
        res = b.call(bm.id, "list_invoices", {"page_size": 200})
        # company-wide on purpose: wider than the manager's ticket scope
        assert {r["id"] for r in res["results"]} == {i.id for i in world.invoices if i.company_id == bm.company_id}


def test_invoice_period_filter():
    w = make_world(1, "train")
    b = MockBackend(w)
    ca = users(w, CA)[0]
    inv = first(i for i in w.invoices if i.company_id == ca.company_id)
    res = b.call(ca.id, "list_invoices", {"period_year": inv.period_year, "period_month": inv.period_month, "page_size": 200})
    assert res["count"] >= 1 and all(r["period"] == f"{inv.period_year}-{inv.period_month:02d}" for r in res["results"])


def test_list_ticket_filters():
    w = make_world(2, "train")
    b = MockBackend(w)
    sa = users(w, SA)[0]
    res = b.call(sa.id, "list_tickets", {"status": ["OPEN"], "page_size": 200})
    assert res["count"] == sum(1 for t in w.tickets if t.status == "OPEN" and not t.archived)
    res = b.call(sa.id, "list_tickets", {"priority": ["URGENT"], "page_size": 200})
    assert all(r["priority"] == "URGENT" for r in res["results"])
    st = users(w, STAFF)[0]
    res = b.call(st.id, "list_tickets", {"my_jobs": True, "page_size": 200})
    assert res["count"] >= 1 and all(st.id in w.ticket(r["id"]).assigned_staff_ids for r in res["results"])
    res = b.call(sa.id, "list_tickets", {"agenda": "today", "page_size": 200})
    assert all(w.ticket(r["id"]).scheduled_date == w.today for r in res["results"])
    stats = b.call(sa.id, "get_ticket_stats", {})
    assert stats["total"] == sum(1 for t in w.tickets if not t.archived)


def test_notifications_are_own():
    w = make_world(1, "train")
    b = MockBackend(w)
    for u in w.users[:6]:
        res = b.call(u.id, "list_notifications", {"page_size": 200})
        assert res["count"] == sum(1 for n in w.notifications if n.recipient_id == u.id)
        assert res["unread_count"] == sum(1 for n in w.notifications if n.recipient_id == u.id and not n.is_read)


# ----------------------------------------------------------- create ticket --
def test_create_ticket_rules(world):
    w = copy.deepcopy(world)
    b = MockBackend(w)
    st = users(w, STAFF)[0]
    c = w.customers[0]
    args = {"title": "Test", "description": "Iets is kapot", "building_id": c.building_ids[0], "customer_id": c.id}
    assert code(b.call(st.id, "create_ticket", args)) == (400, "create_not_allowed")
    cu = users(w, CU)[0]
    own_c = w.customer(cu.customer_id)
    ok = b.call(cu.id, "create_ticket", {**args, "building_id": cu.access_building_ids[0], "customer_id": own_c.id,
                                          "type": "COMPLAINT"})
    assert not is_error(ok) and ok["status"] == "OPEN"
    assert w.ticket(ok["id"]).type == "REPORT"  # customers always create REPORT
    other_c = first(x for x in w.customers if x.id != cu.customer_id)
    assert code(b.call(cu.id, "create_ticket", {**args, "customer_id": other_c.id, "building_id": other_c.building_ids[0]}))[1] == "customer_not_allowed"
    no_access = [x for x in own_c.building_ids if x not in cu.access_building_ids]
    if no_access:
        assert code(b.call(cu.id, "create_ticket", {**args, "customer_id": own_c.id, "building_id": no_access[0]}))[1] == "building_not_allowed"
    bm = users(w, BM)[0]
    outside = first(x for x in w.buildings if x.id not in bm.building_ids and x.is_active)
    linked = first(x for x in w.customers if outside.id in x.building_ids)
    assert code(b.call(bm.id, "create_ticket", {**args, "building_id": outside.id, "customer_id": linked.id}))[1] == "building_not_allowed"
    unlinked = first(x for x in w.customers if bm.building_ids[0] not in x.building_ids)
    assert code(b.call(bm.id, "create_ticket", {**args, "building_id": bm.building_ids[0], "customer_id": unlinked.id}))[1] in ("customer_not_linked",)


# ---------------------------------------------------------------- messages --
def test_message_type_rules(world):
    w = copy.deepcopy(world)
    b = MockBackend(w)
    st = first(u for u in users(w, STAFF) if any(u.id in t.assigned_staff_ids for t in w.tickets))
    t = first(t for t in w.tickets if st.id in t.assigned_staff_ids)
    assert code(b.call(st.id, "add_ticket_message", {"ticket_id": t.id, "message": "x", "message_type": "PUBLIC_REPLY"}))[1] == "message_type_not_allowed"
    res = b.call(st.id, "add_ticket_message", {"ticket_id": t.id, "message": "Sleutel ligt bij receptie"})
    assert res["message_type"] == "STAFF_OPERATIONAL"  # role default for staff
    cca = first(u for u in users(w, CCA) if u.customer_id == t.customer_id)
    assert code(b.call(cca.id, "add_ticket_message", {"ticket_id": t.id, "message": "x", "message_type": "INTERNAL_NOTE"}))[1] == "message_type_not_allowed"
    assert b.call(cca.id, "add_ticket_message", {"ticket_id": t.id, "message": "x"})["message_type"] == "PUBLIC_REPLY"
    assert b.call(cca.id, "add_ticket_message", {"ticket_id": t.id, "message": "x", "message_type": "CUSTOMER_INTERNAL"})["message_type"] == "CUSTOMER_INTERNAL"
    other = first(x for x in users(w, CCA) if x.customer_id != t.customer_id)
    assert code(b.call(other.id, "add_ticket_message", {"ticket_id": t.id, "message": "x"}))[0] == 404


# ------------------------------------------------------------ transitions --
def fresh(world):
    w = copy.deepcopy(world)
    return w, MockBackend(w)


def test_customer_can_only_decide(world):
    w, b = fresh(world)
    cu = users(w, CU)[0]
    t = first(t for t in w.tickets if t.created_by == cu.id and t.status == "WAITING_CUSTOMER_APPROVAL")
    assert code(b.call(cu.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "CLOSED"})) == (403, "customer_status_not_allowed")
    assert code(b.call(cu.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "REJECTED"}))[1] == "rejection_note_required"
    assert set(allowed_next_statuses(w, cu, t)) == {"APPROVED", "REJECTED"}
    res = b.call(cu.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "APPROVED"})
    assert res["status"] == "APPROVED" and w.ticket(t.id).status == "APPROVED"


def test_customer_cannot_decide_when_not_waiting(world):
    w, b = fresh(world)
    cu = users(w, CU)[0]
    t = first(t for t in w.tickets if t.created_by == cu.id and t.status == "OPEN")
    assert allowed_next_statuses(w, cu, t) == []
    assert code(b.call(cu.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "APPROVED"}))[1] == "forbidden_transition"


def test_location_manager_decides_for_location(world):
    w, b = fresh(world)
    clm = users(w, CLM)[0]
    t = first(t for t in w.tickets if t.customer_id == clm.customer_id and t.building_id in clm.access_building_ids
              and t.status == "WAITING_CUSTOMER_APPROVAL" and t.created_by != clm.id)
    res = b.call(clm.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "REJECTED", "note": "Nog vies"})
    assert res["status"] == "REJECTED"


def test_provider_decision_needs_override_reason(world):
    w, b = fresh(world)
    t = first(t for t in w.tickets if t.status == "WAITING_CUSTOMER_APPROVAL")
    ca = first(u for u in users(w, CA) if u.company_id == t.company_id)
    assert code(b.call(ca.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "APPROVED"}))[1] == "override_reason_required"
    assert b.call(ca.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "APPROVED", "override_reason": "Klant akkoord per telefoon"})["status"] == "APPROVED"


def test_bm_override_can_be_revoked():
    for s in TRAIN_SEEDS:
        w = make_world(s, "train")
        b = MockBackend(w)
        for bm in users(w, BM):
            if bm.bm_may_override:
                continue
            t = next((t for t in w.tickets if t.building_id in bm.building_ids and t.status == "WAITING_CUSTOMER_APPROVAL"), None)
            if not t:
                continue
            assert "APPROVED" not in allowed_next_statuses(w, bm, t)
            assert code(b.call(bm.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "APPROVED", "override_reason": "x"}))[1] == "bm_override_disabled"
            return
    pytest.skip("no revoked BM with a waiting ticket")


def test_bm_cannot_close_or_reopen(world):
    w, b = fresh(world)
    for bm in users(w, BM):
        t = next((t for t in w.tickets if t.building_id in bm.building_ids and t.status == "APPROVED"), None)
        if t:
            assert "CLOSED" not in allowed_next_statuses(w, bm, t)
            assert code(b.call(bm.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "CLOSED"}))[1] == "forbidden_transition"
            ca = first(u for u in users(w, CA) if u.company_id == t.company_id)
            assert b.call(ca.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "CLOSED"})["status"] == "CLOSED"
            return
    pytest.skip("no approved ticket in a BM building")


def test_staff_transitions(world):
    w, b = fresh(world)
    st = first(u for u in users(w, STAFF) if any(u.id in t.assigned_staff_ids and t.status == "IN_PROGRESS" for t in w.tickets))
    t = first(t for t in w.tickets if st.id in t.assigned_staff_ids and t.status == "IN_PROGRESS")
    route = w.building(t.building_id).staff_completion_route
    wrong = ({"WAITING_MANAGER_REVIEW", "WAITING_CUSTOMER_APPROVAL"} - {route}).pop()
    assert code(b.call(st.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "ON_HOLD"}))[1] == "forbidden_transition"
    assert code(b.call(st.id, "change_ticket_status", {"ticket_id": t.id, "to_status": wrong, "note": "klaar"}))[1] == "staff_completion_route_mismatch"
    assert code(b.call(st.id, "change_ticket_status", {"ticket_id": t.id, "to_status": route}))[1] == "completion_note_required"
    assert b.call(st.id, "change_ticket_status", {"ticket_id": t.id, "to_status": route, "note": "Alles schoon"})["status"] == route
    # a ticket the staff member can see but is not assigned to
    other = next((x for x in w.tickets if can_see_ticket(w, st, x) and st.id not in x.assigned_staff_ids
                  and x.status == "ACKNOWLEDGED"), None)
    if other:
        assert code(b.call(st.id, "change_ticket_status", {"ticket_id": other.id, "to_status": "IN_PROGRESS"}))[1] == "forbidden_transition"


def test_start_needs_assignee(world):
    w, b = fresh(world)
    t = first(t for t in w.tickets if t.status == "OPEN" and not t.assigned_staff_ids)
    ca = first(u for u in users(w, CA) if u.company_id == t.company_id)
    assert code(b.call(ca.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "IN_PROGRESS"}))[1] == "transition_requirements_unmet"
    assert b.call(ca.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "ACKNOWLEDGED"})["status"] == "ACKNOWLEDGED"
    assert code(b.call(ca.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "ACKNOWLEDGED"}))[1] == "no_op_transition"


def test_super_admin_out_of_table_needs_reason(world):
    w, b = fresh(world)
    sa = users(w, SA)[0]
    t = first(t for t in w.tickets if t.status == "OPEN")
    assert code(b.call(sa.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "CLOSED"}))[1] == "override_reason_required"
    assert b.call(sa.id, "change_ticket_status", {"ticket_id": t.id, "to_status": "CLOSED", "override_reason": "Dubbele melding"})["status"] == "CLOSED"
    ca = first(u for u in users(w, CA) if u.company_id == t.company_id)
    t2 = first(x for x in w.tickets if x.status == "OPEN" and x.company_id == ca.company_id and x.id != t.id)
    assert code(b.call(ca.id, "change_ticket_status", {"ticket_id": t2.id, "to_status": "CLOSED", "override_reason": "x"}))[1] == "forbidden_transition"


def test_allowed_next_statuses_agree_with_execution():
    """For every role and every visible ticket: a status listed in allowed_next_statuses never fails
    with forbidden_transition / 403, and a status not listed always fails."""
    w0 = make_world(1, "train")
    for u in w0.users:
        for t0 in visible_tickets(w0, u)[:12]:
            allowed = set(allowed_next_statuses(w0, u, t0))
            for to in ["IN_PROGRESS", "ACKNOWLEDGED", "ON_HOLD", "WAITING_MANAGER_REVIEW", "WAITING_CUSTOMER_APPROVAL",
                       "APPROVED", "REJECTED", "CLOSED", "REOPENED_BY_ADMIN"]:
                if to == t0.status:
                    continue
                w = copy.deepcopy(w0)
                t = w.ticket(t0.id)
                t.assigned_staff_ids = t.assigned_staff_ids or [0]  # satisfy the assignee requirement
                res = MockBackend(w).call(u.id, "change_ticket_status", {"ticket_id": t.id, "to_status": to,
                                                                         "note": "n", "override_reason": "r"})
                ok = not is_error(res)
                if u.role == SA and t0.status != "CONVERTED_TO_EXTRA_WORK":
                    assert ok  # super admin may move anything with a reason
                else:
                    assert ok == (to in allowed), (u.role, t0.status, to, res)


# ------------------------------------------------------------- extra work --
def test_extra_work_decisions(world):
    w, b = fresh(world)
    cu = users(w, CU)[0]
    e = first(e for e in w.extra_work if e.created_by == cu.id and e.status == "PRICING_PROPOSED")
    det = b.call(cu.id, "get_extra_work_request", {"extra_work_id": e.id})
    assert det["can_approve"] and det["can_reject"] and det["decision_needs_reason"] is False
    assert code(b.call(cu.id, "decide_extra_work", {"extra_work_id": e.id, "decision": "reject"}))[1] == "rejection_note_required"
    assert b.call(cu.id, "decide_extra_work", {"extra_work_id": e.id, "decision": "approve"})["status"] == "CUSTOMER_APPROVED"
    assert code(b.call(cu.id, "decide_extra_work", {"extra_work_id": e.id, "decision": "approve"}))[1] == "invalid_transition"
    st = users(w, STAFF)[0]
    e2 = first(x for x in w.extra_work if x.status == "PRICING_PROPOSED" and x.id != e.id)
    assert code(b.call(st.id, "decide_extra_work", {"extra_work_id": e2.id, "decision": "approve"}))[0] == 404
    ca = first(u for u in users(w, CA) if u.company_id == e2.company_id)
    assert code(b.call(ca.id, "decide_extra_work", {"extra_work_id": e2.id, "decision": "approve"}))[1] == "override_reason_required"
    assert b.call(ca.id, "decide_extra_work", {"extra_work_id": e2.id, "decision": "approve", "reason": "Akkoord per mail"})["status"] == "CUSTOMER_APPROVED"


def test_customer_cannot_decide_other_customers_extra_work(world):
    w, b = fresh(world)
    cca = users(w, CCA)[0]
    e = first(x for x in w.extra_work if x.customer_id != cca.customer_id and x.status == "PRICING_PROPOSED")
    assert code(b.call(cca.id, "decide_extra_work", {"extra_work_id": e.id, "decision": "approve"})) == (404, "not_found")
    assert w.ew(e.id).status == "PRICING_PROPOSED"


def test_unknown_tool_and_user():
    w = make_world(1, "train")
    b = MockBackend(w)
    assert code(b.call(999999, "list_tickets", {}))[0] == 401
    assert code(b.call(w.users[0].id, "delete_everything", {}))[0] == 404


def test_tool_sets_match_public_schema():
    import json, pathlib
    spec = json.loads((pathlib.Path(__file__).parents[1] / "tools" / "tools_v1.json").read_text(encoding="utf-8"))
    names = {t["name"]: t["access"] for t in spec["tools"]}
    assert set(names) == READ_TOOLS | WRITE_TOOLS
    assert {n for n, a in names.items() if a == "write"} == WRITE_TOOLS


def test_transition_table_shape():
    assert len(TRANSITIONS) == 16
    assert TRANSITIONS[("APPROVED", "CLOSED")] == {SA, CA}
