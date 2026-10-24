"""Supply lines, trade routes and the ships that keep colonies alive.

Supply lines (supply()): a country's power reaches its far provinces only by road and rail from the centre: past
SUPPLY_FREE degrees from its capital (over its own landmass) its land gets less and less of it (1 / (1 + distance
past that / SUPPLY_HALF), never below SUPPLY_MIN) - less of its materials reach the treasury (economy.py), its
garrisons fight with less behind them (engine._bites: SUPPLY_FIGHT) and its machines go without spare parts
(tech.py).  Land on another landmass (an expedition's beachhead, an overseas territory) is exempt: it has hardly any
contact with home and lives on what it has (and the occasional ship, below).

Trade routes (routes(), every TRADE_EVERY days): countries at peace that like each other well enough (diplomacy.py:
TRADE_OPINION) trade - neighbours over the border, countries with working ports by sea (TRADE_SEA degrees between
their capitals, TRADE_SAIL tech at both ends: tech.py), the most promising TRADE_MAX partners each.  Each route adds
TRADE_BONUS to a country's materials income (half that to its food) up to TRADE_MOST, food goes from a partner with
plenty to one going short (TRADE_FOOD_*), knowledge flows from the better-off to the other (tech.py), the two grow
friendlier (diplomacy.py) - and epidemics travel along the route too (disease.carry).  The map draws them as thin
lines between the capitals ('g' shows or hides them).

Resupply (world.outposts): a colony founded across the sea, or an expedition's beachhead, has no road home - but every
RESUPPLY_GAP days or so a ship comes from the old country with RESUPPLY_PEOPLE new colonists (from the old country's
people), materials and food, while the old country is safe and can spare it (RESUPPLY_COST), not in the depth of a
frozen winter at the colony, and until the colony stands on its own (RESUPPLY_UNTIL people, or RESUPPLY_YEARS).
Pirates near the colony may take the ship (PIRATE_TAKE).  The ship is drawn off the colony's coast for a few days.
"""
import numpy as np

SUPPLY_EVERY = 20
SUPPLY_FREE = 8.0
SUPPLY_HALF = 25.0
SUPPLY_MIN = 0.35
SUPPLY_FIGHT = 0.15
SUPPLY_MATERIALS = 0.5     # (economy.py: materials x 1 - this x (1 - supply))
TRADE_EVERY = 30
TRADE_MAX = 3
TRADE_SEA = 40.0
TRADE_SAIL = 0.25
TRADE_OPINION = -0.1
TRADE_BONUS = 0.05
TRADE_MOST = 0.15
TRADE_FOOD_RICH = 90       # (days of food: a partner with more than this sells ...
TRADE_FOOD_POOR = 30       #  ... to one with less than this ...
TRADE_FOOD_SHARE = 0.15    #  ... this share of its surplus)
TRADE_MOOD = 0.03
TRADE_DANGER = 0.35
RESUPPLY_EVERY = 5
RESUPPLY_GAP = (60, 150)
RESUPPLY_PEOPLE = 40
RESUPPLY_MATERIALS = 15.0
RESUPPLY_FOOD = 30         # days of the colony's eating
RESUPPLY_COST = 12.0
RESUPPLY_UNTIL = 3000
RESUPPLY_YEARS = 4
RESUPPLY_DANGER = 0.35
RESUPPLY_ICE = 0.6         # (snow at the colony this deep: the harbour is frozen - the ship waits)
SHIP_DAYS = 12
PIRATE_TAKE = 0.25
PIRATE_NEAR = 45


def _deg(world, r0, c0, rr, cc):
    import expeditions
    return expeditions._deg(world, r0, c0, rr, cc)


# ------------------------------------------------------------------------------------------------ supply lines
def supply(world):
    """0..1 per tile: how much of its country's power reaches it (1 off any country, or overseas).  None before the
    first reckoning."""
    s = getattr(world, "supply_map", None)
    if s is None or s.shape != world.H.shape or world.ticks - getattr(world, "_supply_t", -10 ** 6) >= SUPPLY_EVERY:
        if not getattr(world, "ai", True):
            return None
        s = _supply(world)
    return s


def _supply(world):
    n = len(world.civs)
    S = world.statics
    cr, cc = np.zeros(n), np.zeros(n)
    mass = np.full(n, -1, dtype=np.int64)
    for c in world.civs:
        if c.id and c.capital is not None and not c.collapsed:
            cr[c.id], cc[c.id] = c.capital
            mass[c.id] = S.landmass[c.capital]
    O = world.O
    rr, col = np.indices(O.shape)
    o = O
    res = float(world.meta.get("res", 0.5)) if getattr(world, "meta", None) else 0.5
    dr = (rr - cr[o]) * res
    dc = np.abs(col - cc[o])
    if world.wrap:
        dc = np.minimum(dc, world.cols - dc)
    b = world.meta.get("bounds") if getattr(world, "meta", None) else None   # (east-west degrees shrink away from
    lat = (b[3] - (np.arange(world.rows) + 0.5) * res) if b else np.zeros(world.rows)   # the equator)
    coslat = np.cos(np.radians(lat)).astype(np.float32)
    dc = dc * res * coslat[:, None]
    d = np.hypot(dr, dc)
    f = 1.0 / (1.0 + np.maximum(d - SUPPLY_FREE, 0) / SUPPLY_HALF)
    f = np.clip(f, SUPPLY_MIN, 1.0)
    home = (o > 0) & (mass[o] >= 0) & (S.landmass == mass[o])
    out = np.where(home, f, 1.0).astype(np.float32)
    world.supply_map, world._supply_t = out, world.ticks
    return out


# ------------------------------------------------------------------------------------------------ trade routes
def routes(world):
    return world.__dict__.setdefault("trade", {})


def _live(c):
    return bool(c.id and c.ai and not c.collapsed and not c.is_anarchy and c.m and c.m.get("n")
                and c.capital is not None)


def _can_trade(world, a, b, touching):
    import war
    import diplomacy
    import tech
    if war.key(a.id, b.id) in world.wars or a.threat(a.m) > TRADE_DANGER or b.threat(b.m) > TRADE_DANGER:
        return 0.0
    if diplomacy.opinion(world, a.id, b.id) < TRADE_OPINION or diplomacy.opinion(world, b.id, a.id) < TRADE_OPINION:
        return 0.0
    border = touching.get((min(a.id, b.id), max(a.id, b.id)), 0)
    if border >= war.MIN_BORDER:
        return 1.0
    if a.ports > 0 and b.ports > 0 and min(tech.civ_level(a), tech.civ_level(b)) >= TRADE_SAIL:
        d = float(_deg(world, a.capital[0], a.capital[1], np.array([b.capital[0]]), np.array([b.capital[1]]))[0])
        if d <= TRADE_SEA:
            return 0.6 * (1.0 - d / (2 * TRADE_SEA))
    return 0.0


def step(world):
    supply(world)
    if world.ticks % RESUPPLY_EVERY == 0:
        _resupply(world)
    if world.ticks % TRADE_EVERY:
        return
    import war
    import diplomacy
    import disease
    rt = routes(world)
    touching = war.contacts(world)
    live = [c for c in world.civs if _live(c)]
    by_id = {c.id: c for c in live}
    for k in list(rt):                                    # routes that no longer hold
        a, b = tuple(k)
        if a not in by_id or b not in by_id or _can_trade(world, by_id[a], by_id[b], touching) <= 0:
            del rt[k]
    count = {c.id: 0 for c in live}
    for k in rt:
        for i in k:
            count[i] = count.get(i, 0) + 1
    cand = []
    pairs = set(touching)
    ported = [c for c in live if c.ports > 0]
    for i, a in enumerate(ported):
        for b in ported[i + 1:]:
            pairs.add((min(a.id, b.id), max(a.id, b.id)))
    for a_id, b_id in sorted(pairs):
        a, b = by_id.get(a_id), by_id.get(b_id)
        if a is None or b is None or frozenset((a_id, b_id)) in rt:
            continue
        q = _can_trade(world, a, b, touching)
        if q <= 0:
            continue
        score = q + 0.5 * (diplomacy.opinion(world, a_id, b_id) + diplomacy.opinion(world, b_id, a_id))
        cand.append((score, a_id, b_id))
    cand.sort(reverse=True)
    for score, a_id, b_id in cand:
        if count[a_id] >= TRADE_MAX or count[b_id] >= TRADE_MAX:
            continue
        rt[frozenset((a_id, b_id))] = world.ticks
        count[a_id] += 1
        count[b_id] += 1
    for c in world.civs:
        c.trade_bonus = min(TRADE_MOST, TRADE_BONUS * count.get(c.id, 0)) if c.id in by_id else 0.0
    for k in rt:
        a, b = (by_id[i] for i in k)
        diplomacy.change(world, a.id, b.id, mood=TRADE_MOOD)
        diplomacy.change(world, b.id, a.id, mood=TRADE_MOOD)
        _food(a, b)
        disease.carry(world, a, b)


def _food(a, b):
    for rich, poor in ((a, b), (b, a)):
        if rich.food is None or poor.food is None or rich.food_use <= 0 or poor.food_use <= 0:
            continue
        if rich.food > TRADE_FOOD_RICH * rich.food_use and poor.food < TRADE_FOOD_POOR * poor.food_use:
            q = min((rich.food - TRADE_FOOD_RICH * rich.food_use) * TRADE_FOOD_SHARE,
                    (TRADE_FOOD_POOR * poor.food_use - poor.food))
            if q > 0:
                rich.food -= q
                poor.food += q


# ------------------------------------------------------------------------------------------------ resupply
def outposts(world):
    return world.__dict__.setdefault("outposts", [])


def register(world, parent, r, c, colony=None):
    """A settlement across the sea from `parent`: its ships will come (colony: the new state's id; None: `parent`'s
    own beachhead)."""
    S = world.statics
    if parent.capital is None or S.landmass[r, c] == S.landmass[parent.capital]:
        return
    lo, hi = RESUPPLY_GAP
    outposts(world).append(dict(parent=parent.id, colony=colony, r=int(r), c=int(c), since=world.ticks,
                                next=world.ticks + world.pyrng.randint(lo, hi), ships=0, alive=True))


def ships(world):
    """(r, c) of every supply ship at anchor now."""
    return [(r, c) for r, c, until in getattr(world, "supply_ships", []) if until >= world.ticks]


def _resupply(world):
    import war
    import diplomacy
    import seasons
    obs = outposts(world)
    world.supply_ships = [s for s in getattr(world, "supply_ships", []) if s[2] >= world.ticks]
    for x in obs:
        if not x["alive"] or world.ticks < x["next"]:
            continue
        lo, hi = RESUPPLY_GAP
        x["next"] = world.ticks + world.pyrng.randint(lo, hi)
        p = world.civs[x["parent"]]
        col = world.civs[x["colony"]] if x["colony"] is not None else p
        if p.collapsed or not p.ai or col.collapsed:
            x["alive"] = False
            continue
        cpop = col.m.get("pop", 0) if col.m else 0
        target = _landing(world, x, col)
        if x["colony"] is not None and (cpop >= RESUPPLY_UNTIL or world.ticks - x["since"] > RESUPPLY_YEARS * 365):
            x["alive"] = False
            world.note(f"{col.name} stands on its own - the ships from {p.name} stop coming")
            continue
        if target is None:
            x["alive"] = False
            continue
        if (war.key(p.id, col.id) in world.wars or (col is not p and diplomacy.opinion(world, p.id, col.id) < -0.2)
                or p.threat(p.m) > RESUPPLY_DANGER or p.materials < RESUPPLY_COST + 20 or p.ports <= 0):
            continue
        if seasons.snow(world)[target] >= RESUPPLY_ICE:
            x["next"] = world.ticks + 30                  # (the harbour is frozen: the ship comes in the spring)
            continue
        import expeditions
        if not expeditions.draw_from_home(world, p, RESUPPLY_PEOPLE):
            continue
        p.materials -= RESUPPLY_COST
        sea = _sea_by(world, *target)
        if _pirates(world, target):
            x["ships"] += 1
            world.war_note(f"PIRATES seize a supply ship from {p.name} bound for {col.name}")
            if sea is not None:
                import globalaffairs
                globalaffairs.mark(world, *sea, "piracy")
            continue
        r, c = target
        world.H[r, c] = min(255, int(world.H[r, c]) + RESUPPLY_PEOPLE)
        col.materials += RESUPPLY_MATERIALS
        if col.food is not None and col.food_use > 0:
            col.food += RESUPPLY_FOOD * col.food_use
        x["ships"] += 1
        if col is not p:
            diplomacy.change(world, col.id, p.id, mood=0.05)
        if sea is not None:
            world.supply_ships.append((sea[0], sea[1], world.ticks + SHIP_DAYS))
        if x["ships"] == 1 or x["ships"] % 4 == 0:
            what = f"{col.name}" if col is not p else f"its men at {_place(world, target)}"
            world.note(f"a ship from {p.name} brings {world.people(RESUPPLY_PEOPLE)} colonists and supplies to {what}")


def _place(world, rc):
    from fracture import _place as pl
    return pl(world, rc)


def _landing(world, x, col):
    """Where the ship puts in: the colony's capital, or the beachhead's best-held tile near where it landed."""
    if x["colony"] is not None:
        return col.capital if col.capital is not None and world.O[col.capital] == col.id else None
    r, c = x["r"], x["c"]
    r0, r1, c0, c1 = max(r - 6, 0), min(world.rows, r + 7), max(c - 6, 0), min(world.cols, c + 7)
    mine = (world.O[r0:r1, c0:c1] == col.id) & (world.H[r0:r1, c0:c1] > 10)
    if not mine.any():
        return None
    i = int(np.argmax(np.where(mine, world.H[r0:r1, c0:c1], -1)))
    a, b = divmod(i, c1 - c0)
    return (r0 + a, c0 + b)


def _sea_by(world, r, c):
    r0, r1, c0, c1 = max(r - 4, 0), min(world.rows, r + 5), max(c - 4, 0), min(world.cols, c + 5)
    water = np.argwhere(~world.statics.land[r0:r1, c0:c1])
    if not water.size:
        return None
    j = int(np.argmin(np.abs(water[:, 0] - (r - r0)) + np.abs(water[:, 1] - (c - c0))))
    return (int(water[j, 0] + r0), int(water[j, 1] + c0))


def _pirates(world, rc):
    import crime
    for g in crime.active(world):
        if g["kind"] == "pirates" and abs(g["r"] - rc[0]) + abs(g["c"] - rc[1]) <= PIRATE_NEAR:
            if world.pyrng.random() < PIRATE_TAKE:
                g["wealth"] = g.get("wealth", 0.0) + RESUPPLY_MATERIALS
                return True
    return False
