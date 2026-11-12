"""Seeded synthetic CleanOps world.

A world has two provider companies, each with buildings, customers (linked to
some of the company's buildings), users for all seven roles, tickets in every
status, ticket messages, extra-work requests (some with a quote waiting for
the customer), invoices in several states and notifications.

Everything is deterministic from the seed. Train worlds and test worlds use
disjoint name pools and disjoint id ranges, so no test entity, id or name can
appear in the training data.
"""
from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field, asdict
from typing import Optional

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
SA, CA, BM, STAFF = "SUPER_ADMIN", "COMPANY_ADMIN", "BUILDING_MANAGER", "STAFF"
CU, CLM, CCA = "CUSTOMER_USER", "CUSTOMER_LOCATION_MANAGER", "CUSTOMER_COMPANY_ADMIN"
PROVIDER_ROLES = (SA, CA, BM, STAFF)
CUSTOMER_ROLES = (CU, CLM, CCA)
ALL_ROLES = PROVIDER_ROLES + CUSTOMER_ROLES

ROLE_LABEL = {
    SA: "super admin",
    CA: "company admin (service provider)",
    BM: "building manager (service provider)",
    STAFF: "field staff (service provider)",
    CU: "customer user",
    CLM: "customer location manager",
    CCA: "customer company admin",
}

TICKET_STATUSES = ["OPEN", "ACKNOWLEDGED", "IN_PROGRESS", "ON_HOLD", "WAITING_MANAGER_REVIEW",
                   "WAITING_CUSTOMER_APPROVAL", "REJECTED", "APPROVED", "CLOSED",
                   "REOPENED_BY_ADMIN", "CONVERTED_TO_EXTRA_WORK"]
OPEN_STATUSES = ["OPEN", "ACKNOWLEDGED", "IN_PROGRESS", "ON_HOLD", "WAITING_MANAGER_REVIEW",
                 "WAITING_CUSTOMER_APPROVAL", "REOPENED_BY_ADMIN"]
EW_STATUSES = ["REQUESTED", "UNDER_REVIEW", "PRICING_PROPOSED", "CUSTOMER_APPROVED", "IN_PROGRESS",
               "COMPLETED", "CUSTOMER_REJECTED", "CANCELLED"]
MESSAGE_TYPES = ["PUBLIC_REPLY", "INTERNAL_NOTE", "STAFF_OPERATIONAL", "STAFF_COMPLETION", "CUSTOMER_INTERNAL"]

# ---------------------------------------------------------------------------
# Name pools: TRAIN and TEST are disjoint on purpose.
# ---------------------------------------------------------------------------
POOLS = {
    "train": dict(
        companies=["Glansdienst", "Noordster Facilitair", "Brightway Cleaning", "Van Dijk Schoonmaak",
                   "Kristal Services", "Eiland Facility", "Polderglans", "Spotless Partners"],
        cities=["Utrecht", "Amersfoort", "Zwolle", "Haarlem", "Leiden", "Delft", "Arnhem", "Nijmegen",
                "Breda", "Tilburg", "Groningen", "Apeldoorn"],
        bnames=["Rivierzicht", "De Hoven", "Lindeplein", "Spoorzicht", "Het Baken", "Oostpoort", "De Linie",
                "Parkweide", "Molenhof", "Zonnehof", "Westergracht", "Havenkade", "Beukenrode", "De Kolk"],
        btypes=["Kantoor", "Bedrijfsverzamelgebouw", "Campus", "Zorgcentrum", "School", "Winkelcentrum"],
        streets=["Lindelaan", "Stationsweg", "Kerkstraat", "Industrieweg", "Marktplein", "Dorpsstraat",
                 "Parallelweg", "Molenweg"],
        customers=["Bakkerij Jansen", "Advocatenkantoor Visser", "Huisartsenpraktijk De Linde",
                   "Stichting Welzijn Oost", "Techno Parts BV", "Groen & Co", "Boekhandel Pagina", "Fysio Fit",
                   "Architectenbureau Lijn", "Hotel De Brug", "Notariaat Smit", "Dataflow BV",
                   "Kinderopvang Zonnestraal", "Garage Bakker", "Restaurant De Gouden Lepel", "Accountants Mulder"],
        first=["Sanne", "Daan", "Emma", "Lucas", "Julia", "Thijs", "Lotte", "Bram", "Fleur", "Ruben", "Iris",
               "Jesse", "Noor", "Milan", "Sara", "Tim", "Anouk", "Kevin", "Mila", "Joris", "Yara", "Mehmet",
               "Fatima", "Tom", "Esther", "Sem"],
        last=["de Vries", "Jansen", "Bakker", "Visser", "Smit", "Meijer", "de Boer", "Mulder", "de Groot",
              "Bos", "Vos", "Peters", "Hendriks", "van Leeuwen", "Dekker", "Brouwer", "Yilmaz", "Kaya"],
        tickets=[
            ("Lekkende kraan in de pantry", "De kraan in de pantry blijft druppelen.", "Pantry 1e verdieping"),
            ("Zeepdispenser leeg", "De zeepdispenser in het toilet is leeg en moet worden bijgevuld.", "Toilet begane grond"),
            ("Verstopte wc", "De wc op de tweede verdieping is verstopt.", "Toilet 2e verdieping"),
            ("Prullenbakken niet geleegd", "De prullenbakken in de vergaderzaal zijn vrijdag niet geleegd.", "Vergaderzaal 3"),
            ("Vlekken op tapijt", "Er zitten koffievlekken op het tapijt bij de ingang.", "Entree"),
            ("Ramen binnenzijde vuil", "De ramen aan de binnenkant zijn al weken niet gewassen.", "Kantoortuin"),
            ("Kapotte tl-buis", "In de gang knippert een tl-buis.", "Gang west"),
            ("Glas in fietsenstalling", "Er ligt glas op de grond in de fietsenstalling.", "Fietsenstalling"),
            ("Stank in keuken", "In de keuken hangt een rare lucht bij de afvoer.", "Keuken"),
            ("Handdoekrol op", "De handdoekrol in de herentoiletten is op.", "Herentoilet"),
            ("Liftvloer vies", "De vloer van de lift is erg vies.", "Lift A"),
            ("Trappenhuis niet gestofzuigd", "Het trappenhuis is deze week overgeslagen.", "Trappenhuis oost"),
            ("Spinnenwebben bij entree", "Bij de hoofdingang hangen overal spinnenwebben.", "Hoofdingang"),
            ("Koffieautomaat lekt", "Onder de koffieautomaat staat een plas water.", "Koffiecorner"),
            ("Graffiti op gevel", "Er is graffiti gespoten naast de achterdeur.", "Achtergevel"),
            ("Vuile vergadertafels", "De tafels in de vergaderruimte zijn plakkerig.", "Vergaderzaal 1"),
            ("Afvalcontainer vol", "De papiercontainer is overvol.", "Binnenplaats"),
            ("Douche schimmel", "In de douche van de kleedkamer zit schimmel.", "Kleedkamer"),
            ("Broken door closer", "The door closer on the meeting room door is broken.", "Meeting room 2"),
            ("Dirty windows lobby", "The lobby windows have not been cleaned for a while.", "Lobby"),
            ("Bins not emptied", "The bins on the third floor were not emptied yesterday.", "Third floor"),
            ("Water on the floor", "There is water on the floor next to the sink.", "Kitchen"),
            ("Muizenkeutels in magazijn", "In het magazijn liggen muizenkeutels.", "Magazijn"),
            ("Kauwgom op trap", "Op de buitentrap zit veel kauwgom.", "Buitentrap"),
            ("Ventilatierooster stoffig", "De ventilatieroosters zitten vol stof.", "Serverruimte"),
            ("Toiletpapier ontbreekt", "Er is geen reserve toiletpapier meer.", "Damestoilet"),
        ],
        extra_work=[
            ("Glasbewassing buitenzijde", "Eenmalig de ramen aan de buitenkant wassen."),
            ("Dieptereiniging tapijt", "Tapijt in de kantoortuin dieptereinigen."),
            ("Opleveringsschoonmaak verbouwing", "Schoonmaak na de verbouwing van de tweede verdieping."),
            ("Extra schoonmaak open dag", "Extra ronde schoonmaak voor de open dag."),
            ("Vloer strippen en waxen", "Linoleum vloer strippen en opnieuw in de was zetten."),
            ("Bureaus reinigen na verhuizing", "Alle bureaus reinigen na de interne verhuizing."),
            ("Graffiti verwijderen", "Graffiti van de gevel laten verwijderen."),
            ("Extra toiletronde evenement", "Extra toiletronde tijdens het personeelsfeest."),
            ("Window cleaning atrium", "Clean the glass roof of the atrium once."),
            ("Carpet shampoo meeting rooms", "Shampoo the carpets of all meeting rooms."),
            ("Zonwering reinigen", "Buitenzonwering aan de zuidzijde reinigen."),
            ("Parkeergarage vegen", "Parkeergarage machinaal laten vegen."),
        ],
    ),
    "test": dict(
        companies=["Helderwerk Facility", "Zuidkust Reiniging", "Clearline Services", "Meridiaan Schoonmaak"],
        cities=["Eindhoven", "Maastricht", "Almere", "Deventer", "Alkmaar", "Den Bosch"],
        bnames=["Kraaiennest", "De Wending", "Veldzicht", "Brugwachter", "Torenhoek", "Lichtenberg",
                "Waterpoort", "De Smidse"],
        btypes=["Kantoor", "Bedrijvenhof", "Gezondheidscentrum", "Hogeschool", "Showroom"],
        streets=["Wilhelminalaan", "Havenstraat", "Bleekveld", "Ringbaan"],
        customers=["Opticien Helder", "Dansschool Ritme", "Zorggroep Horizon", "Logistiek Vos BV",
                   "Apotheek De Vijzel", "Studio Kade", "Vertaalbureau Babel", "Sportschool Kracht"],
        first=["Lieke", "Gijs", "Maud", "Stijn", "Roos", "Koen", "Femke", "Niels", "Ilse", "Wouter", "Hanna",
               "Rik", "Amira", "Youssef", "Vera", "Olaf"],
        last=["Kuiper", "Willems", "van Dam", "Schouten", "Prins", "Huisman", "Koster", "Verbeek", "Postma",
              "Özdemir", "Lambregts", "Timmer"],
        tickets=[
            ("Plafondplaat los", "Een plafondplaat in de wachtruimte hangt los.", "Wachtruimte"),
            ("Urinoir verstopt", "Het urinoir in het herentoilet loopt niet door.", "Herentoilet 1e"),
            ("Bladeren bij ingang", "Bij de ingang ligt een dikke laag natte bladeren.", "Ingang noord"),
            ("Spiegel gebarsten", "De spiegel in de dameskleedkamer is gebarsten.", "Dameskleedkamer"),
            ("Brandblusser vies", "De brandblussers in de gang zijn erg stoffig.", "Gang 2"),
            ("Vaatwasser ruikt", "De vaatwasser in de kantine ruikt muf.", "Kantine"),
            ("Sticky floor canteen", "The floor of the canteen is sticky after lunch.", "Canteen"),
            ("Fingerprints on glass doors", "The glass doors at reception are full of fingerprints.", "Reception"),
            ("Duivenpoep op balkon", "Het balkon ligt vol duivenpoep.", "Balkon 3e"),
            ("Kalkaanslag in douches", "In alle douches zit kalkaanslag.", "Doucheruimte"),
            ("Natte vlek plafond", "Er zit een natte vlek op het plafond van de archiefkamer.", "Archief"),
            ("Deurmat versleten", "De deurmat bij de personeelsingang is versleten en vies.", "Personeelsingang"),
            ("Overflowing sanitary bins", "The sanitary bins in the ladies' room are overflowing.", "Ladies room"),
            ("Koelkast niet schoon", "De koelkast in de pantry is al lang niet schoongemaakt.", "Pantry"),
        ],
        extra_work=[
            ("Gevelreiniging hoogwerker", "Gevel aan de straatkant reinigen met een hoogwerker."),
            ("Bouwschoonmaak nieuwe vleugel", "Schoonmaak van de nieuwe vleugel na oplevering."),
            ("Stoelen stomen", "Alle stoffen stoelen in de kantine stomen."),
            ("Post-event clean-up", "Clean the hall after the customer event."),
            ("Dakgoten leeghalen", "Dakgoten van het bijgebouw leeghalen."),
            ("Desinfectie na griepgolf", "Extra desinfectie van deurklinken en bureaus."),
        ],
    ),
}

FAMILY_ID_RANGE = {"train": (11, 2400), "test": (3100, 8800)}


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
@dataclass
class Company:
    id: int
    name: str


@dataclass
class Building:
    id: int
    company_id: int
    name: str
    city: str
    address: str
    postal_code: str
    is_active: bool = True
    # where a staff member's "work done" report goes next
    staff_completion_route: str = "WAITING_MANAGER_REVIEW"


@dataclass
class Customer:
    id: int
    company_id: int
    name: str
    building_ids: list
    contact_email: str
    lifecycle: str = "ACTIVE"


@dataclass
class User:
    id: int
    full_name: str
    email: str
    role: str                         # one of the 7 persona roles (ALL_ROLES)
    company_id: Optional[int] = None  # provider users
    building_ids: list = field(default_factory=list)       # BM: managed buildings
    staff_visibility: dict = field(default_factory=dict)   # STAFF: building_id -> ASSIGNED_ONLY | BUILDING_READ
    customer_id: Optional[int] = None                       # customer users
    access_building_ids: list = field(default_factory=list)  # CU / CLM: buildings with an access row
    bm_may_override: bool = True       # BM: may decide on the customer's behalf (with a reason)
    language: str = "nl"

    @property
    def is_customer(self) -> bool:
        return self.role in CUSTOMER_ROLES


@dataclass
class Ticket:
    id: int
    ticket_no: str
    company_id: int
    building_id: int
    customer_id: int
    title: str
    description: str
    room_label: str
    type: str
    priority: str
    status: str
    created_by: int
    created_at: str
    updated_at: str
    assigned_staff_ids: list = field(default_factory=list)
    manager_id: Optional[int] = None
    scheduled_date: Optional[str] = None
    archived: bool = False
    customer_wanted_date: Optional[str] = None
    history: list = field(default_factory=list)


@dataclass
class Message:
    id: int
    ticket_id: int
    author_id: int
    message_type: str
    message: str
    created_at: str


@dataclass
class ExtraWork:
    id: int
    company_id: int
    building_id: int
    customer_id: int
    title: str
    description: str
    status: str
    created_by: int
    requested_at: str
    deadline: Optional[str]
    routing_decision: str
    request_intent: str
    lines: list
    has_sent_quote: bool = False
    decision_reason: Optional[str] = None

    @property
    def total_amount(self) -> float:
        return round(sum(l["qty"] * l["unit_price"] for l in self.lines), 2)


@dataclass
class Invoice:
    id: int
    number: str
    company_id: int
    customer_id: int
    building_id: Optional[int]
    status: str
    period_year: int
    period_month: int
    lines: list

    @property
    def subtotal(self) -> float:
        return round(sum(l["amount"] for l in self.lines), 2)


@dataclass
class Notification:
    id: int
    recipient_id: int
    title: str
    ticket_id: Optional[int]
    extra_work_id: Optional[int]
    is_read: bool
    created_at: str


@dataclass
class World:
    seed: int
    family: str
    today: str
    companies: list
    buildings: list
    customers: list
    users: list
    tickets: list
    messages: list
    extra_work: list
    invoices: list
    notifications: list

    # simple lookups -------------------------------------------------------
    def user(self, uid):
        return next((u for u in self.users if u.id == uid), None)

    def building(self, bid):
        return next((b for b in self.buildings if b.id == bid), None)

    def customer(self, cid):
        return next((c for c in self.customers if c.id == cid), None)

    def company(self, cid):
        return next((c for c in self.companies if c.id == cid), None)

    def ticket(self, tid):
        return next((t for t in self.tickets if t.id == tid), None)

    def ew(self, eid):
        return next((e for e in self.extra_work if e.id == eid), None)

    def invoice(self, iid):
        return next((i for i in self.invoices if i.id == iid), None)

    def users_with_role(self, role):
        return [u for u in self.users if u.role == role]

    def all_ids(self) -> set:
        out = set()
        for coll in (self.companies, self.buildings, self.customers, self.users, self.tickets, self.messages,
                     self.extra_work, self.invoices, self.notifications):
            out.update(x.id for x in coll)
        return out

    def to_dict(self):
        return asdict(self)


class _Ids:
    """Increasing id sequences per entity type, with random gaps."""

    def __init__(self, rng, lo, hi):
        self.rng = rng
        self.next = {}
        span = (hi - lo) // 10
        for i, kind in enumerate(["company", "building", "customer", "user", "ticket", "message", "ew",
                                  "invoice", "notification", "ticket_no"]):
            self.next[kind] = lo + i * span + rng.randint(0, span // 3)

    def __call__(self, kind):
        v = self.next[kind]
        self.next[kind] += self.rng.randint(1, 3)
        return v


def _date(today: dt.date, days_ago: int) -> str:
    return (today - dt.timedelta(days=days_ago)).isoformat()


def make_world(seed: int, family: str = "train", today: str = "2026-11-12") -> World:
    """Build a deterministic world. family is 'train' or 'test'."""
    assert family in POOLS
    rng = random.Random(f"{family}-{seed}")
    pool = POOLS[family]
    lo, hi = FAMILY_ID_RANGE[family]
    nid = _Ids(rng, lo, hi)
    tday = dt.date.fromisoformat(today)

    used_names = set()

    def person():
        while True:
            n = f"{rng.choice(pool['first'])} {rng.choice(pool['last'])}"
            if n not in used_names:
                used_names.add(n)
                return n

    def email(name, domain):
        return name.lower().replace(" ", ".").replace("ö", "o").replace("ü", "u") + "@" + domain

    companies, buildings, customers, users = [], [], [], []
    tickets, messages, extra_work, invoices, notifications = [], [], [], [], []

    comp_names = rng.sample(pool["companies"], 2)
    bnames = rng.sample(pool["bnames"], len(pool["bnames"]))
    cust_names = rng.sample(pool["customers"], len(pool["customers"]))

    users.append(User(nid("user"), person(), "", SA, language=rng.choice(["nl", "en"])))
    users[-1].email = email(users[-1].full_name, "platform.example")

    for ci, cname in enumerate(comp_names):
        comp = Company(nid("company"), cname)
        companies.append(comp)
        domain = cname.lower().replace(" ", "") + ".example"
        n_b = rng.choice([3, 4])
        cbuild = []
        for _ in range(n_b):
            nm = bnames.pop()
            b = Building(nid("building"), comp.id, f"{rng.choice(pool['btypes'])} {nm}", rng.choice(pool["cities"]),
                         f"{rng.choice(pool['streets'])} {rng.randint(1, 140)}",
                         f"{rng.randint(1000, 9899)} {rng.choice('ABCDEFGHJKLMNPRSTVWXZ')}{rng.choice('ABCDEFGHJKLMNPRSTVWXZ')}",
                         staff_completion_route=rng.choice(["WAITING_MANAGER_REVIEW"] * 3 + ["WAITING_CUSTOMER_APPROVAL"]))
            buildings.append(b)
            cbuild.append(b)
        if rng.random() < 0.5:  # an inactive building, only a super admin sees it
            nm = bnames.pop()
            buildings.append(Building(nid("building"), comp.id, f"{rng.choice(pool['btypes'])} {nm}",
                                      rng.choice(pool["cities"]), f"{rng.choice(pool['streets'])} 1", "1000 AA",
                                      is_active=False))
        # customers: each linked to 1-3 buildings, every building has >= 1 customer
        n_c = rng.choice([2, 3])
        ccust = []
        for k in range(n_c):
            k_b = rng.randint(1, min(3, len(cbuild)))
            linked = sorted(b.id for b in rng.sample(cbuild, k_b))
            c = Customer(nid("customer"), comp.id, cust_names.pop(), linked, "")
            c.contact_email = "info@" + c.name.lower().replace(" ", "").replace("&", "en") + ".example"
            customers.append(c)
            ccust.append(c)
        for b in cbuild:
            if not any(b.id in c.building_ids for c in ccust):
                ccust[rng.randrange(len(ccust))].building_ids.append(b.id)
        for c in ccust:
            c.building_ids.sort()
        if rng.random() < 0.4:
            ccust[-1].lifecycle = rng.choice(["ONBOARDING", "NOTICE"])

        # provider users
        u = User(nid("user"), person(), "", CA, company_id=comp.id, language=rng.choice(["nl", "nl", "en"]))
        users.append(u)
        bms = []
        shuffled = rng.sample(cbuild, len(cbuild))
        split = rng.randint(1, len(cbuild) - 1)
        for part in (shuffled[:split], shuffled[split:]):
            u = User(nid("user"), person(), "", BM, company_id=comp.id, building_ids=sorted(b.id for b in part),
                     language=rng.choice(["nl", "nl", "en"]))
            users.append(u)
            bms.append(u)
        bms[rng.randrange(2)].bm_may_override = False
        staff = []
        for level in ("BUILDING_READ", rng.choice(["ASSIGNED_ONLY", "BUILDING_READ"])):
            vis = {b.id: level for b in rng.sample(cbuild, rng.randint(2, len(cbuild)))}
            u = User(nid("user"), person(), "", STAFF, company_id=comp.id, staff_visibility=vis,
                     language=rng.choice(["nl", "nl", "en"]))
            users.append(u)
            staff.append(u)

        # customer users: per customer one CCA, one CLM, and one or two CUs
        for c in ccust:
            cdom = c.contact_email.split("@")[1]
            users.append(User(nid("user"), person(), "", CCA, customer_id=c.id, access_building_ids=list(c.building_ids),
                              language=rng.choice(["nl", "nl", "en"])))
            users.append(User(nid("user"), person(), "", CLM, customer_id=c.id,
                              access_building_ids=sorted(rng.sample(c.building_ids, rng.randint(1, len(c.building_ids)))),
                              language=rng.choice(["nl", "nl", "en"])))
            for _ in range(rng.choice([1, 2])):
                users.append(User(nid("user"), person(), "", CU, customer_id=c.id,
                                  access_building_ids=sorted(rng.sample(c.building_ids, rng.randint(1, len(c.building_ids)))),
                                  language=rng.choice(["nl", "nl", "en"])))
            for uu in users:
                if uu.customer_id == c.id and not uu.email:
                    uu.email = email(uu.full_name, cdom)
        for uu in users:
            if not uu.email:
                uu.email = email(uu.full_name, domain)

    # ------------------------------------------------------------------
    # Tickets
    # ------------------------------------------------------------------
    status_weights = [("OPEN", 4), ("ACKNOWLEDGED", 2), ("IN_PROGRESS", 3), ("ON_HOLD", 1),
                      ("WAITING_MANAGER_REVIEW", 2), ("WAITING_CUSTOMER_APPROVAL", 3), ("REJECTED", 1),
                      ("APPROVED", 2), ("CLOSED", 2), ("REOPENED_BY_ADMIN", 1), ("CONVERTED_TO_EXTRA_WORK", 1)]
    st_pop = [s for s, w in status_weights for _ in range(w)]
    topics = pool["tickets"]
    year = tday.year
    for c in customers:
        comp_id = c.company_id
        cusers = [u for u in users if u.customer_id == c.id]
        for bid in c.building_ids:
            creators = [u for u in cusers if u.role == CCA or bid in u.access_building_ids]
            bms_b = [u for u in users if u.role == BM and bid in u.building_ids]
            staff_b = [u for u in users if u.role == STAFF and bid in u.staff_visibility]
            provider_creators = bms_b + [u for u in users if u.role == CA and u.company_id == comp_id]
            n_t = rng.randint(3, 6)
            statuses = rng.sample(st_pop, n_t)
            for st in statuses:
                title, desc, room = rng.choice(topics)
                by_customer = rng.random() < 0.7 and creators
                creator = rng.choice(creators) if by_customer else rng.choice(provider_creators)
                days = rng.randint(0, 80)
                tid = nid("ticket")
                t = Ticket(
                    id=tid, ticket_no=f"TCK-{year}-{nid('ticket_no'):06d}", company_id=comp_id, building_id=bid,
                    customer_id=c.id, title=title, description=desc, room_label=room,
                    type="REPORT" if creator.is_customer else rng.choice(["REPORT", "REQUEST", "COMPLAINT", "OTHER"]),
                    priority=rng.choice(["NORMAL"] * 5 + ["HIGH"] * 2 + ["URGENT"]), status=st,
                    created_by=creator.id, created_at=_date(tday, days),
                    updated_at=_date(tday, max(0, days - rng.randint(0, days))),
                    manager_id=bms_b[0].id if bms_b else None)
                if st != "OPEN" and staff_b and rng.random() < 0.85:
                    t.assigned_staff_ids = [rng.choice(staff_b).id]
                if st in ("ACKNOWLEDGED", "IN_PROGRESS", "ON_HOLD", "REOPENED_BY_ADMIN") or (st == "OPEN" and rng.random() < 0.3):
                    t.scheduled_date = _date(tday, rng.choice([3, 1, 0, 0, -1, -2, -5, -9]))
                if rng.random() < 0.15 and st in ("CLOSED", "APPROVED"):
                    t.archived = rng.random() < 0.5
                t.history = [{"to": "OPEN", "on": t.created_at}] + ([] if st == "OPEN" else [{"to": st, "on": t.updated_at}])
                tickets.append(t)
    tickets.sort(key=lambda t: t.id)

    # make sure every CU has some own tickets, including one waiting for their approval
    for u in users:
        if u.role != CU:
            continue
        own = [t for t in tickets if t.created_by == u.id]
        if not any(t.status == "WAITING_CUSTOMER_APPROVAL" for t in own):
            title, desc, room = rng.choice(topics)
            bid = rng.choice(u.access_building_ids)
            bms_b = [x for x in users if x.role == BM and bid in x.building_ids]
            staff_b = [x for x in users if x.role == STAFF and bid in x.staff_visibility]
            c = next(cc for cc in customers if cc.id == u.customer_id)
            t = Ticket(nid("ticket"), f"TCK-{year}-{nid('ticket_no'):06d}", c.company_id, bid, c.id, title, desc, room,
                       "REPORT", "NORMAL", "WAITING_CUSTOMER_APPROVAL", u.id, _date(tday, rng.randint(5, 30)),
                       _date(tday, rng.randint(0, 4)), [staff_b[0].id] if staff_b else [],
                       bms_b[0].id if bms_b else None)
            t.history = [{"to": "OPEN", "on": t.created_at}, {"to": t.status, "on": t.updated_at}]
            tickets.append(t)
        if not any(t.status in ("OPEN", "IN_PROGRESS") for t in own):
            title, desc, room = rng.choice(topics)
            bid = rng.choice(u.access_building_ids)
            c = next(cc for cc in customers if cc.id == u.customer_id)
            bms_b = [x for x in users if x.role == BM and bid in x.building_ids]
            t = Ticket(nid("ticket"), f"TCK-{year}-{nid('ticket_no'):06d}", c.company_id, bid, c.id, title, desc, room,
                       "REPORT", rng.choice(["NORMAL", "HIGH"]), "OPEN", u.id, _date(tday, rng.randint(0, 10)),
                       _date(tday, 0), [], bms_b[0].id if bms_b else None)
            t.history = [{"to": "OPEN", "on": t.created_at}]
            tickets.append(t)
    # every staff member gets assigned work in ACKNOWLEDGED and IN_PROGRESS
    for u in users:
        if u.role != STAFF:
            continue
        for st in ("ACKNOWLEDGED", "IN_PROGRESS"):
            if any(t.status == st and u.id in t.assigned_staff_ids for t in tickets):
                continue
            cands = [t for t in tickets if t.status == st and t.building_id in u.staff_visibility]
            if cands:
                rng.choice(cands).assigned_staff_ids = [u.id]
            else:
                bid = rng.choice(sorted(u.staff_visibility))
                c = next(cc for cc in customers if bid in cc.building_ids)
                title, desc, room = rng.choice(topics)
                t = Ticket(nid("ticket"), f"TCK-{year}-{nid('ticket_no'):06d}", c.company_id, bid, c.id, title, desc,
                           room, "REPORT", "NORMAL", st,
                           next(x.id for x in users if x.role == CA and x.company_id == c.company_id),
                           _date(tday, rng.randint(2, 20)), _date(tday, 1), [u.id], None, _date(tday, rng.choice([0, 1, -1])))
                t.history = [{"to": "OPEN", "on": t.created_at}, {"to": st, "on": t.updated_at}]
                tickets.append(t)
    tickets.sort(key=lambda t: t.id)
    # ticket numbers increase with creation order of the list (cosmetic), unrelated to ids
    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    msg_texts = {
        "PUBLIC_REPLY": ["We hebben uw melding ontvangen en plannen het in.", "Thanks, we will look at it this week.",
                         "Kunt u aangeven wanneer de ruimte vrij is?", "Graag horen we wanneer het klaar is."],
        "INTERNAL_NOTE": ["Klant belt vaker hierover, prioriteit geven.", "Check contract: valt dit onder meerwerk?"],
        "STAFF_OPERATIONAL": ["Sleutel ophalen bij de receptie.", "Materiaal besteld, komt donderdag.",
                              "Ruimte was op slot, morgen opnieuw."],
        "STAFF_COMPLETION": ["Werk uitgevoerd, alles schoon opgeleverd.", "Done, the area is clean again."],
        "CUSTOMER_INTERNAL": ["Even navragen bij facilitair of dit al eerder gemeld is.", "Intern: budget checken."],
    }
    for t in tickets:
        for _ in range(rng.choice([0, 1, 1, 2, 3])):
            mt = rng.choice(MESSAGE_TYPES)
            if mt == "CUSTOMER_INTERNAL" or (mt == "PUBLIC_REPLY" and rng.random() < 0.5):
                cands = [u for u in users if u.customer_id == t.customer_id]
            elif mt.startswith("STAFF_"):
                cands = [u for u in users if u.id in t.assigned_staff_ids] or \
                        [u for u in users if u.role == BM and t.building_id in u.building_ids]
            else:
                cands = [u for u in users if u.role in (CA, BM) and u.company_id == t.company_id]
            if not cands:
                continue
            messages.append(Message(nid("message"), t.id, rng.choice(cands).id, mt, rng.choice(msg_texts[mt]),
                                    t.updated_at))

    # ------------------------------------------------------------------
    # Extra work
    # ------------------------------------------------------------------
    ew_status_pop = ["REQUESTED", "UNDER_REVIEW", "PRICING_PROPOSED", "PRICING_PROPOSED", "PRICING_PROPOSED",
                     "CUSTOMER_APPROVED", "IN_PROGRESS", "COMPLETED", "CUSTOMER_REJECTED", "CANCELLED"]
    for c in customers:
        cusers = [u for u in users if u.customer_id == c.id]
        for _ in range(rng.randint(2, 4)):
            bid = rng.choice(c.building_ids)
            creators = [u for u in cusers if u.role == CCA or bid in u.access_building_ids]
            title, desc = rng.choice(pool["extra_work"])
            st = rng.choice(ew_status_pop)
            lines = [{"description": title, "qty": rng.choice([1, 2, 4, 8]), "unit_price": float(rng.choice([45, 62.5, 85, 120, 240, 450]))}]
            if rng.random() < 0.4:
                lines.append({"description": "Voorrijkosten", "qty": 1, "unit_price": 35.0})
            routing = rng.choice(["INSTANT", "PROPOSAL", "PROPOSAL"])
            e = ExtraWork(nid("ew"), c.company_id, bid, c.id, title, desc, st, rng.choice(creators).id,
                          _date(tday, rng.randint(1, 60)), _date(tday, rng.randint(-30, 10)), routing,
                          "REQUEST_QUOTE" if routing == "PROPOSAL" else "DIRECT_AGREED_PRICE_ORDER", lines,
                          has_sent_quote=(st == "PRICING_PROPOSED" and routing == "PROPOSAL"))
            extra_work.append(e)
    # every CU owns at least one extra-work request waiting for a price decision
    for u in users:
        if u.role != CU or any(e.created_by == u.id and e.status == "PRICING_PROPOSED" for e in extra_work):
            continue
        c = next(cc for cc in customers if cc.id == u.customer_id)
        title, desc = rng.choice(pool["extra_work"])
        extra_work.append(ExtraWork(nid("ew"), c.company_id, rng.choice(u.access_building_ids), c.id, title, desc,
                                    "PRICING_PROPOSED", u.id, _date(tday, rng.randint(1, 20)),
                                    _date(tday, -rng.randint(5, 25)), "PROPOSAL", "REQUEST_QUOTE",
                                    [{"description": title, "qty": 1, "unit_price": float(rng.choice([180, 275, 640]))}],
                                    has_sent_quote=True))
    extra_work.sort(key=lambda e: e.id)

    # ------------------------------------------------------------------
    # Invoices: last 4 months per customer; older ones SENT, last month ISSUED/SENT, this month DRAFT
    # ------------------------------------------------------------------
    inv_seq = rng.randint(10, 400)
    for c in customers:
        for back in range(4, -1, -1):
            m = tday.month - back
            y = tday.year
            while m <= 0:
                m += 12
                y -= 1
            if back == 0:
                st = "DRAFT"
            elif back == 1:
                st = rng.choice(["ISSUED", "SENT", "SENT"])
            else:
                st = "SENT"
            if rng.random() < 0.15 and back > 0:
                continue
            lines = [{"description": f"Contractschoonmaak {m:02d}-{y}", "amount": float(rng.choice([850, 1240, 1975, 2600, 3150]))}]
            if rng.random() < 0.5:
                lines.append({"description": "Meerwerk", "amount": float(rng.choice([120, 275.5, 480]))})
            inv_seq += 1
            invoices.append(Invoice(nid("invoice"), f"F{y}-{inv_seq:05d}", c.company_id, c.id,
                                    rng.choice(c.building_ids + [None]), st, y, m, lines))
    invoices.sort(key=lambda i: i.id)

    world = World(seed, family, today, companies, buildings, customers, users, tickets, messages, extra_work,
                  invoices, notifications)

    # ------------------------------------------------------------------
    # Notifications: a few per user about things they can see
    # ------------------------------------------------------------------
    from .backend import visible_tickets  # local import to avoid a cycle at module load
    for u in users:
        vis = visible_tickets(world, u)
        for t in rng.sample(vis, min(len(vis), rng.randint(1, 5))):
            notifications.append(Notification(nid("notification"), u.id,
                                              rng.choice(["Status gewijzigd", "Nieuw bericht", "Nieuwe melding",
                                                          "Wacht op goedkeuring"]) + f": {t.ticket_no}",
                                              t.id, None, rng.random() < 0.5, t.updated_at))
    notifications.sort(key=lambda n: n.id)
    return world


TRAIN_SEEDS = list(range(1, 13))       # worlds used for training data
VAL_SEEDS = [101, 102]                 # train family, separate seeds, for validation data
TEST_SEEDS = [1, 2, 3]                 # test family (disjoint pools and id ranges)


def world_for(family: str, seed: int) -> World:
    """The world used for a given family/seed, each with its own 'today'."""
    if family == "test":
        today = dt.date(2026, 12, 7) + dt.timedelta(days=37 * seed)
    else:
        today = dt.date(2026, 2, 3) + dt.timedelta(days=23 * (seed % 100) + (seed // 100) * 11)
    return make_world(seed, family, today.isoformat())
