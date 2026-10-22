"""Organized crime on a large scale: where governments fail, the gangs grow - into fleets, armies and states.

Crime rings (world.rings) take root where there is no government (big stretches of anarchy that the zombies have
left) or where the government is coming apart (motives.instability >= ROOT_UNSTABLE).  At most RINGS_MAX at once
(fewer on small maps).  Each has a base (drawn on the map), a strength (its fighters, 0..1, like an army) and wealth
(materials).  By what is around its base it is:

  pirates       a base on the coast: large fleets that raid coastal towns within PIRATE_REACH tiles of sea - people
                killed and carried off, stores looted - and prey on the shipping of the countries they raid
                (PIRATE_*).
  cartel        smuggling and trafficking: food run into countries short of it (at a price), stores stolen from the
                rich, and people trafficked across shut borders - some of them bitten (SMUGGLE_*, TRAFFIC_*).
                It buys officials: the countries it works in grow less stable.
  paramilitary  an armed movement inside a failing state (or in the anarchy next to one): it ambushes the state's
                soldiers, extorts its towns and takes districts by force (PARA_*).

Any ring strong enough hires out its fighters: mercenaries for a country at war that can pay (MERC_*).  A ring
grows on its income (extortion of the people around its base, loot, smuggling, pay) and spends it on fighters.
Countries strike back: a secure country with an army cracks down on a ring that preys on it or sits on its land
(CRACKDOWN_*) - the commonest end of a ring.  Hordes that reach its base finish it too.

A ring that gets strong and rich enough where nobody governs - or in a state too weak to stop it - becomes a state of
its own (STATE_*): a criminal proto-state (government 'syndicate': strong army, good at trade, unruly, aggressive,
won't merge) - a pirate republic, a cartel state, a militia's territory.  Its ring goes on working from there.
"""
import numpy as np

import motives
from civilization import box_sum

EVERY = 10
RINGS_MAX = 10             # on the world map (x the map's land / RINGS_LAND, at least 2)
RINGS_LAND = 60000         # (land tiles for RINGS_MAX)
ROOT_CHANCE = 0.25         # per check, a new ring where one can take root (while fewer than the most)
ROOT_PEOPLE = 600          # people (map units) within ROOT_REACH of the spot ...
ROOT_REACH = 8
ROOT_UNSTABLE = 0.45       # ... nobody's, or in a state this unstable
ROOT_APART = 40            # tiles from another ring
ROOT_SAFE = 150            # zombies within ROOT_REACH at most
UPKEEP = 0.01              # strength lost per check (fighters drift off)
RECRUIT_COST = 6.0         # wealth per RECRUIT strength
RECRUIT = 0.04
EXTORT = 0.00004           # wealth per person within ROOT_REACH of its base, per check
PIRATE_REACH = 45          # tiles of sea a pirate fleet sails to raid
PIRATE_STRENGTH = 0.2
PIRATE_KILL = 0.08         # share of the people on the raided stretch killed (x (0.5 + strength)) ...
PIRATE_TAKE = 0.06         # ... and carried off
PIRATE_LOOT = 0.06         # share of the country's materials and food looted (materials at most PIRATE_LOOT_MAX)
PIRATE_LOOT_MAX = 15.0
PIRATE_PORTS = 0.04        # the raided country loses this share of its working ports (shipping preyed on)
SMUGGLE_REACH = 40         # tiles (over land, or by sea from a coastal base) to a country it works in
SMUGGLE_FOOD = 0.08        # a hungry country's daily use x SMUGGLE_DAYS of food run in ...
SMUGGLE_DAYS = 10
SMUGGLE_PRICE = 1.5        # ... for this many materials per day's food (x (0.5 + strength))
SMUGGLE_THEFT = 0.03       # share of a rich neighbour's materials stolen
SMUGGLE_CORRUPT = 0.05     # instability it adds to the country it works in
TRAFFIC_PEOPLE = 0.03      # share of the people near its base trafficked across a shut border ...
TRAFFIC_BITTEN = 0.06      # ... some of them bitten
PARA_STRENGTH = 0.25
PARA_KILL = 0.00006        # army strength the state loses per point of the ring's strength x its people nearby
PARA_TAKE = 0.35           # chance per check it takes a district by force (x strength)
PARA_TILES = 6
MERC_STRENGTH = 0.4
MERC_PRICE = 18.0
MERC_ARMY = 0.08
CRACKDOWN_SECURE = 0.45    # (motives.security) a country this secure ...
CRACKDOWN_ARMY = 0.45      # ... with this strong an army ...
CRACKDOWN_CHANCE = 0.3     # ... cracks down (per check, x its army) on a ring that preys on it or sits on its land
CRACKDOWN_HIT = 0.35       # strength the ring loses (x the country's army and strength)
STATE_STRENGTH = 0.6       # a ring this strong ...
STATE_WEALTH = 35.0        # ... and rich ...
STATE_CHANCE = 0.15        # ... may become a state (per check)
STATE_REACH = 7            # its land: nobody's populated land within this many tiles of its base (and a weak host's)
NAMES = {"pirates": ("{p} Corsairs", "Brethren of {p}", "{p} Freebooters", "Black Fleet of {p}"),
         "cartel": ("{p} Cartel", "{p} Syndicate", "{p} Brotherhood", "{p} Combine"),
         "paramilitary": ("{p} Militia", "{p} Black Guard", "{p} Free Legion", "{p} Defense Corps")}
STATE_NAMES = {"pirates": ("Pirate Republic of {p}", "Free Port of {p}"),
               "cartel": ("{p} Cartel State", "Syndicate of {p}"),
               "paramilitary": ("{p} Militia Territory", "{p} Legion")}


def rings(world):
    return world.__dict__.setdefault("rings", [])


def active(world):
    return [g for g in getattr(world, "rings", []) if g.get("alive")]


def _cap(world):
    land = int(world.statics.land.sum())
    return int(max(2, min(RINGS_MAX, round(RINGS_MAX * land / RINGS_LAND))))


def _win(world, r, c, R):
    return slice(max(r - R, 0), min(r + R + 1, world.rows)), slice(max(c - R, 0), min(c + R + 1, world.cols))


def _coastal(world, r, c):
    w = _win(world, r, c, 2)
    return bool((~world.statics.land[w]).any())


def step(world):
    if world.ticks % EVERY or not world.ai or world.ticks < 30:
        return
    live = [g for g in rings(world) if g.get("alive")]
    for g in live:
        _run(world, g)
    live = [g for g in rings(world) if g.get("alive")]
    if len(live) < _cap(world) and world.pyrng.random() < ROOT_CHANCE:
        _root(world, live)


# ------------------------------------------------------------------------------------------------ taking root
def _root(world, live):
    """A new ring where the government has failed: the biggest town nobody governs (or in a state coming apart),
    with people about and no horde."""
    H, O = world.H, world.O
    near_z = world.zombie_near(ROOT_REACH)
    unstable = np.zeros(len(world.civs), dtype=bool)
    for c in world.civs:
        unstable[c.id] = bool(c.id and not c.collapsed and c.ai and motives.instability(c) >= ROOT_UNSTABLE)
    best = None
    for name, r, k, pop in world.cities:
        o = int(O[r, k])
        if H[r, k] <= 20 or near_z[r, k] > ROOT_SAFE or not (o == 0 or unstable[o]):
            continue
        if any(abs(g["r"] - r) + abs(g["c"] - k) < ROOT_APART for g in rings(world)
               if g.get("alive") or world.ticks - g.get("died", -10 ** 6) < 200):
            continue
        w = _win(world, r, k, ROOT_REACH)
        people = int(np.maximum(H[w], 0).sum())
        if people < ROOT_PEOPLE:
            continue
        score = people * (1.0 if o == 0 else 0.6) * (0.5 + world.pyrng.random())
        if best is None or score > best[0]:
            best = (score, name, r, k, o)
    if best is None:
        return
    _, name, r, k, o = best
    if _coastal(world, r, k) and world.pyrng.random() < 0.65:
        kind = "pirates"
    elif o and world.civs[o].gov in ("junta", "warlord") or world.pyrng.random() < 0.4:
        kind = "paramilitary"
    else:
        kind = "cartel"
    from fracture import _place
    place = _place(world, (r, k))
    g = dict(id=len(rings(world)), kind=kind, r=int(r), c=int(k), host=o, born=world.ticks, alive=True,
             strength=0.3, wealth=10.0, place=place, state=None,
             name=world.pyrng.choice(NAMES[kind]).format(p=place))
    rings(world).append(g)
    where = f"the anarchy around {place}" if o == 0 else f"{place}, as {world.civs[o].name} comes apart"
    what = {"pirates": "a pirate fleet", "cartel": "a smuggling cartel", "paramilitary": "an armed militia"}[kind]
    world.war_note(f"CRIME: {what}, the {g['name']}, takes root in {where}")
    import globalaffairs
    globalaffairs.mark(world, r, k, {"pirates": "piracy", "cartel": "smuggling", "paramilitary": "paramilitary"}[kind])


# ------------------------------------------------------------------------------------------------ a ring's work
def _run(world, g):
    import globalaffairs
    H, O = world.H, world.O
    r, k = g["r"], g["c"]
    st = world.civs[g["state"]] if g.get("state") is not None else None
    if st is not None and st.collapsed:
        return _end(world, g, f"falls with {st.name}")
    w = _win(world, r, k, ROOT_REACH)
    z = int(world.zombie_near(3)[r, k])
    people = int(np.maximum(H[w], 0).sum())
    if z > max(60, int(np.maximum(H[max(r - 3, 0):r + 4, max(k - 3, 0):k + 4], 0).sum())):
        return _end(world, g, "is overrun by the hordes")
    if people < 40:
        return _end(world, g, "melts away: nobody left to prey on")
    host = int(O[r, k])
    g["host"] = host
    g["wealth"] += EXTORT * people * (1.0 + g["strength"])
    if host and not world.civs[host].collapsed and st is None:     # (its protection money comes out of the state's)
        hc = world.civs[host]
        hc.materials = max(0.0, hc.materials - EXTORT * people * 0.5)
        hc.instability = min(1.0, getattr(hc, "instability", 0.0) + 0.01)
    g["strength"] = max(0.0, g["strength"] - UPKEEP)
    if g["wealth"] >= RECRUIT_COST and g["strength"] < 1.0:
        n = min(int(g["wealth"] // RECRUIT_COST), 3)
        g["wealth"] -= n * RECRUIT_COST
        g["strength"] = min(1.0, g["strength"] + n * RECRUIT)
    victims = set()
    if g["kind"] == "pirates" and g["strength"] >= PIRATE_STRENGTH:
        victims |= _piracy(world, g)
    elif g["kind"] == "cartel":
        victims |= _smuggle(world, g)
    elif g["kind"] == "paramilitary" and g["strength"] >= PARA_STRENGTH:
        victims |= _insurgency(world, g)
    if g["strength"] >= MERC_STRENGTH:
        _hire_out(world, g)
    g.setdefault("victims", {})
    for v in victims:
        g["victims"][v] = world.ticks
    if _crackdown(world, g):
        return
    if (g.get("state") is None and g["strength"] >= STATE_STRENGTH and g["wealth"] >= STATE_WEALTH
            and world.pyrng.random() < STATE_CHANCE):
        _become_state(world, g)


def _sea_reach(world, g, n):
    from civilization import steps
    R = n + 3
    w = _win(world, g["r"], g["c"], R)
    water = ~world.statics.land[w]
    start = np.zeros(water.shape, dtype=bool)
    rr, cc = g["r"] - (w[0].start or 0), g["c"] - (w[1].start or 0)
    start[max(rr - 2, 0):rr + 3, max(cc - 2, 0):cc + 3] = water[max(rr - 2, 0):rr + 3, max(cc - 2, 0):cc + 3]
    if not start.any():
        return w, None
    d = steps(start, n, through=water).astype(np.int32)
    out = d.copy()                                         # (a coast tile: one on from the water beside it)
    out[1:] = np.minimum(out[1:], d[:-1] + 1)
    out[:-1] = np.minimum(out[:-1], d[1:] + 1)
    out[:, 1:] = np.minimum(out[:, 1:], d[:, :-1] + 1)
    out[:, :-1] = np.minimum(out[:, :-1], d[:, 1:] + 1)
    return w, out


def _piracy(world, g):
    """The fleet raids the richest weakly held stretch of coast within PIRATE_REACH of sea."""
    import globalaffairs
    w, sea = _sea_reach(world, g, PIRATE_REACH)
    if sea is None:
        return set()
    H, O, D = world.H[w], world.O[w], world.D[w]
    own = g.get("state")
    prey = world.statics.land[w] & (sea <= PIRATE_REACH) & (O > 0) & (H > 40) & (D < 6)
    if own is not None:
        prey &= O != own
    if not prey.any():
        return set()
    dense = np.where(prey, box_sum(np.maximum(H, 0), 1) - 30 * D, -10 ** 9)
    if world.stochastic:
        dense = dense + world.rng.random(dense.shape) * 200
    rr, cc = np.unravel_index(int(np.argmax(dense)), dense.shape)
    tgt = world.civs[int(O[rr, cc])]
    r0, r1, c0, c1 = max(rr - 1, 0), rr + 2, max(cc - 1, 0), cc + 2
    block = H[r0:r1, c0:c1]
    s = (0.5 + g["strength"]) * world.jitter(0.3)
    dead = (np.maximum(block, 0) * PIRATE_KILL * s).astype(np.int32)
    taken = (np.maximum(block, 0) * PIRATE_TAKE * s).astype(np.int32)
    block -= dead + taken
    D[r0:r1, c0:c1] = np.maximum(D[r0:r1, c0:c1] - 1, 1)
    loot = min(PIRATE_LOOT_MAX, tgt.materials * PIRATE_LOOT)
    tgt.materials -= loot
    g["wealth"] += loot + float(taken.sum()) * 0.01
    if tgt.food is not None:
        tgt.food -= tgt.food * PIRATE_LOOT * 0.5
    tgt.ports = max(0.0, tgt.ports * (1.0 - PIRATE_PORTS))
    tgt.riot_hit += 1
    world.H[g["r"], g["c"]] = min(255, int(world.H[g["r"], g["c"]]) + int(taken.sum()))   # (captives, to the base)
    R, C = rr + (w[0].start or 0), cc + (w[1].start or 0)
    globalaffairs.mark(world, R, C, "piracy")
    g["raids"] = g.get("raids", 0) + 1
    from fracture import _place
    world.war_note(f"PIRATES: the {g['name']} raid {_place(world, (R, C))} ({tgt.name}): "
                   f"{world.people(dead.sum())} dead, {world.people(taken.sum())} carried off",
                   log=g["raids"] % 3 == 1)
    return {tgt.id}


def _reachable(world, g, reach):
    """Governments with land within `reach` of the base: over land, or by sea from a coastal base."""
    from civilization import steps
    w = _win(world, g["r"], g["c"], reach + 3)           # (the window _sea_reach works in)
    start = np.zeros(world.H[w].shape, dtype=bool)
    start[g["r"] - (w[0].start or 0), g["c"] - (w[1].start or 0)] = True
    near = steps(start, reach, through=world.statics.land[w]) <= reach
    if _coastal(world, g["r"], g["c"]):
        w2, sea = _sea_reach(world, g, reach)
        if sea is not None and w2 == w:
            near |= sea <= reach
    O = world.O[w]
    ids = np.unique(O[near & (O > 0) & (world.H[w] > 10)])
    return [world.civs[int(i)] for i in ids if not world.civs[int(i)].collapsed and world.civs[int(i)].ai]


def _smuggle(world, g):
    """Food run into hungry countries at a price; stores stolen from rich ones; people trafficked past shut borders."""
    import globalaffairs
    import war
    out = set()
    them = [c for c in _reachable(world, g, SMUGGLE_REACH) if c.id != g.get("state") and c.m and c.m.get("n")]
    if not them:
        return out
    hungry = [c for c in them if war.scarcity(c) > 0.3 and c.materials > 5 and c.food is not None]
    if hungry:
        c = max(hungry, key=war.scarcity)
        food = c.food_use * SMUGGLE_DAYS * (0.5 + g["strength"])
        price = min(c.materials * 0.5, SMUGGLE_PRICE * SMUGGLE_DAYS * (0.5 + g["strength"]))
        c.food += food
        c.materials -= price
        g["wealth"] += price
        c.instability = min(1.0, getattr(c, "instability", 0.0) + SMUGGLE_CORRUPT)
        if c.capital is not None:
            globalaffairs.mark(world, *c.capital, "smuggling")
        _note(world, g, f"the {g['name']} smuggle food into {c.name} at a steep price")
    rich = [c for c in them if c.materials > 80]
    if rich:
        c = world.pyrng.choice(rich)
        t = c.materials * SMUGGLE_THEFT * (0.5 + g["strength"])
        c.materials -= t
        g["wealth"] += t
        c.instability = min(1.0, getattr(c, "instability", 0.0) + SMUGGLE_CORRUPT * 0.5)
        out.add(c.id)
    shut = [c for c in them if c.id in (getattr(world, "closed", None) or set())]
    if shut:                                            # trafficking: people moved past a shut border
        c = world.pyrng.choice(shut)
        w = _win(world, g["r"], g["c"], ROOT_REACH)
        H = world.H[w]
        src = (world.O[w] != c.id) & (H > 20)
        n = int((np.maximum(H, 0) * src).sum() * TRAFFIC_PEOPLE)
        tiles = np.argwhere((world.O == c.id) & (world.H > 10) & (world.H < 200))
        if n > 0 and tiles.size:
            go = np.floor(np.where(src, H, 0) * TRAFFIC_PEOPLE).astype(H.dtype)
            H -= go
            n = int(go.sum())
            d = np.abs(tiles[:, 0] - g["r"]) + np.abs(tiles[:, 1] - g["c"])
            tr, tc = tiles[int(np.argmin(d))]
            bitten = int(n * TRAFFIC_BITTEN)
            world.H[tr, tc] = min(255, int(world.H[tr, tc]) + n - bitten)
            world.Z[tr, tc] = min(255, int(world.Z[tr, tc]) + bitten)
            g["wealth"] += n * 0.02
            out.add(c.id)
            globalaffairs.mark(world, int(tr), int(tc), "smuggling")
            _note(world, g, f"the {g['name']} traffic {world.people(n)} people past {c.name}'s shut border")
    return out


def _insurgency(world, g):
    """The militia fights the state it lives in (or the nearest weak one): ambushes, extortion, districts taken."""
    import globalaffairs
    host = g.get("host") or 0
    target = world.civs[host] if host and host != g.get("state") and not world.civs[host].collapsed else None
    if target is None:
        near = [c for c in _reachable(world, g, ROOT_REACH * 2) if c.id != g.get("state")]
        if not near:
            return set()
        target = min(near, key=lambda c: c.military)
    w = _win(world, g["r"], g["c"], ROOT_REACH)
    theirs = (world.O[w] == target.id) & (world.H[w] > 10)
    people = int(np.maximum(world.H[w], 0)[theirs].sum())
    target.military = max(0.0, target.military - PARA_KILL * g["strength"] * min(people, 3000))
    target.riot_hit += 1
    g["wealth"] += 0.002 * people
    target.instability = min(1.0, getattr(target, "instability", 0.0) + 0.02)
    out = {target.id}
    if theirs.any() and world.pyrng.random() < PARA_TAKE * g["strength"] and target.military < g["strength"] + 0.2:
        ys, xs = np.nonzero(theirs)
        d = np.abs(ys + (w[0].start or 0) - g["r"]) + np.abs(xs + (w[1].start or 0) - g["c"])
        pick = np.argsort(d)[:PARA_TILES]
        R, C = ys[pick] + (w[0].start or 0), xs[pick] + (w[1].start or 0)
        owner = g.get("state") or 0
        world.O[R, C] = owner                          # (a state of its own, or no government at all)
        world.D[R, C] = np.minimum(world.D[R, C], 2)
        globalaffairs.mark(world, int(R[0]), int(C[0]), "paramilitary")
        from fracture import _place
        _note(world, g, f"the {g['name']} drive {target.name} out of {_place(world, (int(R[0]), int(C[0])))}",
              always=True)
    return out


def _hire_out(world, g):
    """Mercenaries: a country at war with stores to spare buys the ring's fighters."""
    import globalaffairs
    if world.pyrng.random() >= 0.35 or not world.wars:
        return
    buyers = []
    for w in world.wars.values():
        for side in (w["a"], w["b"]):
            c = world.civs[side]
            if c.ai and not c.collapsed and c.materials >= MERC_PRICE * 2 and side != g.get("state"):
                buyers.append(c)
    if not buyers:
        return
    c = max(buyers, key=lambda x: x.materials)
    c.materials -= MERC_PRICE
    g["wealth"] += MERC_PRICE
    c.military = min(1.0, c.military + MERC_ARMY * g["strength"])
    g["strength"] = max(0.0, g["strength"] - 0.03)
    if c.capital is not None:
        globalaffairs.mark(world, *c.capital, "mercenary")
    _note(world, g, f"{c.name} hires the {g['name']} as mercenaries")


def _crackdown(world, g):
    """A secure country with an army strikes the ring that preys on it or sits on its land.  True if it's finished."""
    import globalaffairs
    recent = {v for v, t in g.get("victims", {}).items() if world.ticks - t <= 60}
    host = int(world.O[g["r"], g["c"]])
    cands = set(recent) | ({host} if host and host != g.get("state") else set())
    best = None
    for i in cands:
        c = world.civs[i]
        if (c.collapsed or not c.ai or c.military < CRACKDOWN_ARMY
                or motives.security(world, c) < CRACKDOWN_SECURE):
            continue
        if best is None or c.military > best.military:
            best = c
    if best is None or world.pyrng.random() >= CRACKDOWN_CHANCE * best.military:
        return False
    hit = CRACKDOWN_HIT * best.military * (0.6 + 0.8 * best.strength) * world.jitter(0.3)
    g["strength"] = max(0.0, g["strength"] - hit)
    g["wealth"] *= 0.7
    best.materials = max(0.0, best.materials - 3.0)
    best.military = max(0.0, best.military - 0.01)
    globalaffairs.mark(world, g["r"], g["c"], "crackdown")
    if g["strength"] <= 0.05:
        _end(world, g, f"is crushed by {best.name}")
        return True
    _note(world, g, f"{best.name} cracks down on the {g['name']}")
    return False


def _become_state(world, g):
    """The ring takes over the land around its base: a criminal proto-state."""
    import govern
    from civilization import steps
    host = int(world.O[g["r"], g["c"]])
    hc = world.civs[host] if host else None
    if hc is not None and (hc.military > g["strength"] or motives.instability(hc) < 0.55):
        return                                          # (a state that can still hold it together keeps its land)
    w = _win(world, g["r"], g["c"], STATE_REACH + 2)
    start = np.zeros(world.H[w].shape, dtype=bool)
    start[g["r"] - (w[0].start or 0), g["c"] - (w[1].start or 0)] = True
    near = steps(start, STATE_REACH, through=world.statics.land[w]) <= STATE_REACH
    Ow = world.O[w]
    take = near & world.statics.land[w] & ((Ow == 0) | (Ow == host)) & (world.H[w] > 10)
    if host:
        take &= (Ow == 0) | (steps(start, STATE_REACH // 2, through=world.statics.land[w]) <= STATE_REACH // 2)
    if int(take.sum()) < 3:
        return
    civ = world.add_civ(morale=7)
    if civ is None:
        return
    mask = np.zeros(world.H.shape, dtype=bool)
    mask[w] = take
    import economy
    civ.successor, civ.founded = True, world.ticks
    civ.root = civ.id
    civ.gov = "syndicate"
    civ.military = max(0.4, g["strength"])
    civ.strength = 0.5
    civ.materials = g["wealth"] * 0.5
    g["wealth"] *= 0.5
    pop = int(np.maximum(world.H[mask], 0).sum())
    civ.food = pop * economy.FOOD_PER_PERSON * 60
    world.O[mask] = civ.id
    world.last_owner[mask] = civ.id
    civ.capital = (g["r"], g["c"])
    civ.place = g["place"]
    used = {c.name for c in world.civs}
    name = world.pyrng.choice(STATE_NAMES[g["kind"]]).format(p=g["place"])
    civ.name = name if name not in used else f"{name} {civ.id}"
    civ.traits["aggression"] = max(civ.traits.get("aggression", 1.0), 1.2)
    g["state"] = civ.id
    if hc is not None:
        import war
        war.declare(world, host, civ.id, "a criminal state on its land", truce_ok=True)
    world.war_note(f"CRIME STATE: the {g['name']} take over the land around {g['place']} - {civ.name} "
                   f"({world.people(pop)} people)" + (f", carved out of {hc.name}" if hc is not None else ""))
    world.note(f"the {g['name']} found {civ.name}, a criminal state")


def _end(world, g, how):
    g["alive"] = False
    g["died"] = world.ticks
    world.war_note(f"CRIME: the {g['name']} {how}")


def _note(world, g, text, always=False):
    g["notes"] = g.get("notes", 0) + 1
    world.war_note(("CRIME: " if not text.startswith("PIRATES") else "") + text, log=always or g["notes"] % 3 == 1)
